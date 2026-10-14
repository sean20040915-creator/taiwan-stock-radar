"""GitHub Actions scheduled entrypoint: python -m scripts.update --require-remote

Writes official latest EOD rows to durable database and technical-only snapshots.
No data is silently replaced by synthetic values on network failures.
"""
from __future__ import annotations
import argparse
from datetime import datetime, date
from zoneinfo import ZoneInfo
from src.sources import fetch_snapshot
from src.storage import database_url, make_engine, store_market_day, load_prices, save_scan, record_run
from src.strategy import scored_frame, latest_scans


def update(require_remote=False):
    url = database_url()
    if require_remote and url.startswith("sqlite"):
        raise RuntimeError("DATABASE_URL is missing: scheduled workflow requires shared PostgreSQL")
    engine = make_engine(url)
    started = datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds")
    errors=[]; success=[]
    for market in ("TWSE","TPEX"):
        try:
            rows=fetch_snapshot(market)
            trading_day=date.fromisoformat(rows[0]["day"])
            age=(datetime.now(ZoneInfo("Asia/Taipei")).date()-trading_day).days
            if age<0 or age>10:
                raise ValueError(f"Unexpected trading-day age: {rows[0]['day']}")
            saved=store_market_day(engine,rows)
            success.append(f"{market} {rows[0]['day']}: {saved} symbols")
        except Exception as exc:
            errors.append(f"{market}: {type(exc).__name__}: {exc}")
    if success:
        try:
            all_prices=load_prices(engine,lookback_calendar_days=180)
            calculated=scored_frame(all_prices)
            latest=latest_scans(calculated)
            if not latest.empty:
                # Only rewrite scan snapshots for markets updated in this invocation.
                latest=latest[latest.market.isin([s.split()[0] for s in success])].copy()
                saved=save_scan(engine,latest)
                success.append(f"Technical snapshots: {saved}")
        except Exception as exc:
            errors.append(f"SCORER: {type(exc).__name__}: {exc}")
    status="FAILED" if not success else ("PARTIAL" if errors else "SUCCESS")
    details=" | ".join(success+errors)
    record_run(engine,started,status,details)
    print(status, details)
    if errors:
        raise RuntimeError(details)
    return details


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--require-remote",action="store_true", help="Fail if DATABASE_URL is not PostgreSQL")
    args=parser.parse_args()
    update(args.require_remote)
