"""Conservative 2024–2026 archive builder (separate from live daily updates).

The progress table is authoritative only for completed fetches. This runner
does not classify holidays, fabricate prices, or infer a valid session from
an empty response. Official calendar reconciliation remains a separate audit.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo

from scripts import backfill as history
from src.storage import database_url, make_engine

DEFAULT_START = date(2024, 10, 21)
DEFAULT_END = date(2026, 10, 19)
MAX_DAYS = 5


def pending_market_weekdays(start: date, end: date, done: set) -> tuple[int, int]:
    """Return incomplete weekday dates and incomplete market/date pairs.

    These are weekday approximations, not verified exchange trading sessions.
    """
    days = pairs = 0
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            missing = sum((cursor.isoformat(), market) not in done
                          for market in ("TWSE", "TPEX"))
            pairs += missing
            days += missing > 0
        cursor += timedelta(days=1)
    return int(days), int(pairs)


def archive_plan(start: date, end: date, days_per_run: int, done: set):
    """Find the first incomplete segment within the manual runner's 31-day bound."""
    if not 1 <= days_per_run <= MAX_DAYS:
        raise ValueError(f"Archive batch size must be 1..{MAX_DAYS}")
    if end < start:
        raise ValueError("Archive end must not precede start")
    missing = history.planned_interval(start, end, days_per_run, done)
    if not missing:
        return None
    first = missing[0]
    return first, min(end, first + timedelta(days=30))


def run_archive(start=DEFAULT_START, end=DEFAULT_END, days_per_run=5,
                min_wait=2.0, require_remote=True, now=None):
    ts = now or datetime.now(ZoneInfo("Asia/Taipei"))
    if isinstance(start, str):
        start = date.fromisoformat(start)
    if isinstance(end, str):
        end = date.fromisoformat(end)
    if start > end or end >= ts.date():
        raise ValueError("Archive range must be increasing and end before today")
    if start < ts.date() - timedelta(days=1096):
        raise ValueError("Archive range must stay within three calendar years")
    if not 1 <= days_per_run <= MAX_DAYS:
        raise ValueError(f"Archive batch size must be 1..{MAX_DAYS}")
    if min_wait < 2:
        raise ValueError("Archive minimum interval is 2 seconds")
    url = database_url()
    if require_remote and url.startswith("sqlite"):
        raise RuntimeError("DATABASE_URL missing: remote archive requires PostgreSQL")
    engine = make_engine(url)
    try:
        done = history._completed(engine)
        missing_dates, missing_pairs = pending_market_weekdays(start, end, done)
        print(f"ARCHIVE_STATUS {start}..{end}: "
              f"{missing_dates} missing weekdays; "
              f"{missing_pairs} missing market/weekday pairs", flush=True)
        plan = archive_plan(start, end, days_per_run, done)
    finally:
        engine.dispose()
    if plan is None:
        print(f"ARCHIVE_COMPLETE {start}..{end}: no missing market/weekday pairs",
              flush=True)
        return {"complete": True, "missing_weekdays": 0, "missing_pairs": 0}
    first, last = plan
    print(f"ARCHIVE_RESUME {first}..{last}; max {days_per_run} weekdays "
          f"per run, min wait {min_wait} sec", flush=True)
    # Leverage the already field-tested, resumable storage/validation logic.
    outcome = history.backfill(
        days_per_run=days_per_run, lookback_days=730,
        min_wait=min_wait, require_remote=require_remote, now=ts,
        start_date=first, end_date=last,
    )
    print(f"ARCHIVE_BATCH_DONE saved={outcome['saved']}, "
          f"no_session_reports={outcome['no_session']}, "
          f"errors={outcome['errors']}", flush=True)
    return {"complete": False, "missing_weekdays_before": missing_dates,
            "missing_pairs_before": missing_pairs, **outcome}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default=DEFAULT_START.isoformat())
    parser.add_argument("--end-date", default=DEFAULT_END.isoformat())
    parser.add_argument("--days-per-run", type=int, default=5)
    parser.add_argument("--min-wait", type=float, default=2.0)
    parser.add_argument("--require-remote", action="store_true")
    args = parser.parse_args()
    run_archive(start=args.start_date, end=args.end_date,
                days_per_run=args.days_per_run, min_wait=args.min_wait,
                require_remote=args.require_remote)
