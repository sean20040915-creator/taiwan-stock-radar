from datetime import date, datetime
from zoneinfo import ZoneInfo
import pytest
from scripts import backfill as job


def test_manual_window_oldest_first_and_resume():
    done={("2024-10-21","TWSE"),("2024-10-21","TPEX")}
    picked=job.planned_interval(date(2024,10,21),date(2024,10,25),2,done)
    assert picked==[date(2024,10,22),date(2024,10,23)]
    assert job.planned_interval(date(2024,10,21),date(2024,10,21),2,done)==[]


@pytest.mark.parametrize("start,end",[
    ("2024-10-21",None),(None,"2024-10-25"),
    ("2024-10-25","2024-10-21"),
    ("2024-10-01","2024-11-05"),
    ("2026-10-20","2026-10-20"),
    ("2022-01-01","2022-01-04"),
])
def test_invalid_manual_window_rejected_before_database(start,end):
    with pytest.raises(ValueError):
        job.backfill(now=datetime(2026,10,20,12,tzinfo=ZoneInfo("Asia/Taipei")),
                     start_date=start,end_date=end)


def test_existing_daily_planner_unchanged():
    assert job.planned_days(date(2026,10,20),2,210,set())==[
        date(2026,10,19),date(2026,10,16)]
