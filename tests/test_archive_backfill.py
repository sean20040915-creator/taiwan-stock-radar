from datetime import date, datetime
from zoneinfo import ZoneInfo
import pytest
from scripts import archive_backfill as archive


def test_archive_uses_first_missing_dates_and_skips_completed():
    start, end = date(2024,10,21), date(2024,10,25)
    done = {(d.isoformat(), market) for d in (date(2024,10,21), date(2024,10,22))
            for market in ("TWSE","TPEX")}
    assert archive.pending_market_weekdays(start,end,done) == (3,6)
    assert archive.archive_plan(start,end,2,done) == (date(2024,10,23),date(2024,10,25))


def test_archive_complete_after_all_dates():
    start,end=date(2024,10,21),date(2024,10,25)
    done={(date(2024,10,d).isoformat(),m) for d in range(21,26)
          for m in ("TWSE","TPEX")}
    assert archive.pending_market_weekdays(start,end,done)==(0,0)
    assert archive.archive_plan(start,end,5,done) is None


def test_archive_counts_partially_complete_market():
    d=date(2024,10,21)
    assert archive.pending_market_weekdays(d,d,{(d.isoformat(),"TWSE")})==(1,1)


def test_pilot_bounded_to_31_days():
    first,end=archive.archive_plan(date(2024,10,21),date(2026,10,19),5,set())
    assert first==date(2024,10,21)
    assert (end-first).days == 30


@pytest.mark.parametrize("start,end",[
    ("2026-10-19","2026-10-20"),
    ("2026-10-20","2026-10-19"),
    ("2022-01-01","2022-01-02"),
])
def test_invalid_archive_date_range_rejected(start,end):
    with pytest.raises(ValueError):
        archive.run_archive(start,end,now=datetime(2026,10,20,12,
                                 tzinfo=ZoneInfo("Asia/Taipei")))


def test_no_database_fallback_when_remote_required(monkeypatch):
    monkeypatch.setattr(archive,"database_url",lambda:"sqlite://")
    with pytest.raises(RuntimeError,match="DATABASE_URL"):
        archive.run_archive(now=datetime(2026,10,20,12,
                                         tzinfo=ZoneInfo("Asia/Taipei")))
