"""Resumable, rate-limited historical EOD warm-up for GitHub Actions.

Usage: python -m scripts.backfill --days-per-run 7 --lookback-days 210 --require-remote
No automatic fallback to fake/DEMO prices. On error records are NOT marked done.
"""
from __future__ import annotations
import argparse
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import MetaData, Table, Column, String, PrimaryKeyConstraint, select
from src.historical import NoSessionData, client, fetch_historical_day
from src.storage import make_engine, database_url, store_market_day, load_prices, save_scan, record_run
from src.strategy import scored_frame, latest_scans

progress_metadata=MetaData()
progress=Table("historical_backfill_progress",progress_metadata,
    Column("day",String(10),nullable=False),Column("market",String(8),nullable=False),
    Column("status",String(16),nullable=False),Column("detail",String(250)),
    PrimaryKeyConstraint("day","market"))


def _completed(engine):
    progress_metadata.create_all(engine)
    with engine.connect() as cx:
        rows = cx.execute(select(progress.c.day, progress.c.market, progress.c.status)).all()
    # Historical V3.1 misread TPEx's valid "ok" status as NO_SESSION.
    # Never skip a date based on only one market saying it was closed.
    done = {(r.day, r.market) for r in rows if r.status == "SUCCESS"}
    no_session = {(r.day, r.market) for r in rows if r.status == "NO_SESSION"}
    confirmed_closed_days = {day for day, market in no_session
                             if (day, "TWSE") in no_session and (day, "TPEX") in no_session}
    done.update((day, market) for day in confirmed_closed_days for market in ("TWSE", "TPEX"))
    return done


def _mark(engine, day, market, status, detail):
    from src.storage import _upsert_rows
    with engine.begin() as cx:
        _upsert_rows(cx,progress,[{"day":day,"market":market,"status":status,"detail":detail[:250]}],["day","market"])


def planned_days(today,days_per_run,lookback_days,done):
    # All weekdays; no session on exchange holidays is safely recorded separately.
    # Backfill most recent first so score becomes useful after fewer runs.
    d=today-timedelta(days=1) # Never backfill today while it may be unsettled.
    dates=[]
    while d>=today-timedelta(days=lookback_days) and len(dates)<days_per_run:
        if d.weekday()<5 and any((d.isoformat(),market) not in done for market in ("TWSE","TPEX")):
            dates.append(d)
        d-=timedelta(days=1)
    return dates


def backfill(days_per_run=8,lookback_days=210,min_wait=1.5,require_remote=False,now=None):
    if not 1<=days_per_run<=25: raise ValueError("days_per_run must be 1..25")
    if not 30<=lookback_days<=730: raise ValueError("lookback_days must be 30..730")
    if min_wait<1.0: raise ValueError("min_wait must be >= 1 second to avoid aggressive requests")
    url=database_url()
    if require_remote and url.startswith("sqlite"):
        raise RuntimeError("DATABASE_URL missing: remote backfill requires PostgreSQL")
    engine=make_engine(url)
    done=_completed(engine)
    ts=now or datetime.now(ZoneInfo("Asia/Taipei"))
    started=ts.isoformat(timespec="seconds")

    dates=planned_days(ts.date(),days_per_run,lookback_days,done)

    # 晚間優先補抓當天缺漏的官方行情
    if ts.hour >= 20 and ts.date().weekday() < 5:
        today_str = ts.date().isoformat()
        if any(
            (today_str, market) not in done
            for market in ("TWSE", "TPEX")
        ):
            dates = [ts.date()] + dates[:days_per_run - 1]
    if not dates:
        print("DONE: no missing weekdays in configured window")
        return {"saved":0,"no_session":0,"errors":0,"requested_dates":0}
    session=client(); saved=no_session=errors=0; messages=[]
    # Abort further requests to an upstream after a failure; do NOT mass retry 403s.
    failed_markets=set()
    for d in dates:
        for market in ("TWSE","TPEX"):
            key=(d.isoformat(),market)
            if key in done or market in failed_markets: continue
            try:
                rows=fetch_historical_day(session,market,d)
                count=store_market_day(engine,rows)
                _mark(engine,d.isoformat(),market,"SUCCESS",f"{count} rows")
                saved+=count
                print(f"SUCCESS {market} {d.isoformat()} {count} rows",flush=True)
            except NoSessionData as e:
                _mark(engine,d.isoformat(),market,"NO_SESSION",str(e))
                no_session+=1
                print(f"NO_SESSION {market} {d.isoformat()} ({str(e)[:90]})",flush=True)
            except Exception as e:
                errors+=1
                failed_markets.add(market)
                messages.append(f"{market} {d.isoformat()}: {type(e).__name__}: {str(e)[:160]}")
                print(f"ERROR {messages[-1]}",flush=True)
            finally:
                time.sleep(min_wait)
    # Recompute current candidates when enough history was added, but existing
    # primary daily-update still refreshes the latest scan each evening.
    if saved:
        try:
            frame=load_prices(engine,lookback_calendar_days=180)
            scored=scored_frame(frame)
            current=latest_scans(scored)
            if not current.empty: save_scan(engine,current)
        except Exception as exc:
            errors+=1
            messages.append(f"SCORER: {type(exc).__name__}: {str(exc)[:160]}")
    status="SUCCESS" if not errors else "PARTIAL"
    detail=f"historical: {len(dates)} dates; {saved} price rows; {no_session} no-session reports; {errors} errors"
    record_run(engine,started,status,detail + " | " + " | ".join(messages))
    print(status,detail,flush=True)
    if errors:
        raise RuntimeError("Backfill incomplete. Unsuccessful market dates will be retried: " + " | ".join(messages))
    return {"saved":saved,"no_session":no_session,"errors":errors,"requested_dates":len(dates)}


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--days-per-run",type=int,default=8)
    p.add_argument("--lookback-days",type=int,default=210)
    p.add_argument("--min-wait",type=float,default=1.5)
    p.add_argument("--require-remote",action="store_true")
    args=p.parse_args()
    backfill(args.days_per_run,args.lookback_days,args.min_wait,args.require_remote)
