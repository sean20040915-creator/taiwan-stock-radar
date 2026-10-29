from datetime import date
import pandas as pd
import pytest
from sqlalchemy import create_engine
from src.storage import metadata, prices
from src.data_audit import (
    analyze_archive_coverage, backtest_data_gate, read_daily_counts,
)


def test_missing_not_auto_holiday():
    frame=pd.DataFrame([
        {"市場":"TWSE","日期":"2025-01-02","行情筆數":1000,"異常OHLCV筆數":0},
        {"市場":"TPEX","日期":"2025-01-02","行情筆數":800,"異常OHLCV筆數":0},
    ])
    summary, details=analyze_archive_coverage(frame,date(2025,1,1),date(2025,1,3))
    assert set(details.loc[details["日期"]=="2025-01-01","狀態"])=={"已登記休市"}
    assert set(details.loc[details["日期"]=="2025-01-03","狀態"])=={"缺資料／未登記休市（待核實）"}
    assert summary["未確認缺漏平日"].tolist()==[1,1]
    assert backtest_data_gate(summary)[0] is False


def test_low_row_count_and_bad_ohlcv_flagged():
    df=pd.DataFrame([
        {"市場":"TWSE","日期":"2025-01-02","行情筆數":1000,"異常OHLCV筆數":0},
        {"市場":"TWSE","日期":"2025-01-03","行情筆數":10,"異常OHLCV筆數":1},
    ])
    summary,detail=analyze_archive_coverage(df,date(2025,1,2),date(2025,1,3))
    assert "OHLCV異常" in detail.iloc[1]["狀態"]
    assert summary.loc[summary["市場"]=="TWSE","異常交易日"].iloc[0]==1


def test_grouped_sql_reads_without_mutation():
    engine=create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as cx:
        cx.execute(prices.insert().values(day="2025-01-02",market="TWSE",code="1111",
              name="X",open=10,high=12,low=9,close=11,volume=100,amount=1000,source="test"))
        cx.execute(prices.insert().values(day="2025-01-02",market="TWSE",code="2222",
              name="Y",open=10,high=9,low=8,close=11,volume=100,amount=1000,source="test"))
    df=read_daily_counts(engine,date(2025,1,2),date(2025,1,3))
    assert len(df)==1
    assert df.iloc[0]["行情筆數"]==2
    assert df.iloc[0]["異常OHLCV筆數"]==1


def test_empty_archive_reports_uncertainty():
    summary,detail=analyze_archive_coverage(pd.DataFrame(columns=["市場","日期","行情筆數","異常OHLCV筆數"]),date(2025,1,1),date(2025,1,3))
    assert len(detail)==6
    assert backtest_data_gate(summary)[0] is False


def test_invalid_range():
    with pytest.raises(ValueError):
        analyze_archive_coverage(pd.DataFrame(),date(2025,1,4),date(2025,1,1))
