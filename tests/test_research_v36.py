from datetime import date
import pandas as pd
import pytest
from sqlalchemy import create_engine
from src.storage import metadata, prices, load_prices_between
from src.research_v36 import research_integrity


def _sample(missing_market=None, missing_stock=None, spike=False):
    rows=[]
    days=pd.bdate_range("2026-03-02",periods=80)
    for i,day in enumerate(days):
        if i==missing_market:
            continue
        for j in range(110):
            code=f"{j:04d}"
            if missing_stock==(i,j):
                continue
            value=100.0 if not(spike and j==0 and i==70) else 160.0
            rows.append(dict(day=day.date().isoformat(),market="TWSE",
                code=code,name="Test",open=value,high=value,low=value,
                close=value,volume=1000.,amount=1e8,score=49,
                bars=i+1,setup=(i==68 and j==0),trigger=False))
    return pd.DataFrame(rows),days[68].date()


def test_clean_contiguous_65_plus_5():
    data,signal=_sample()
    result=research_integrity(data,signal,signal)
    assert len(result)==1
    assert result.iloc[0]["判定"].startswith("僅可描述性")
    assert result.iloc[0]["後5日收盤變動(%)"]==0


def test_missing_whole_market_weekday_blocks_horizon():
    data,signal=_sample(missing_market=70)
    r=research_integrity(data,signal,signal)
    assert r.iloc[0]["判定"]=="市場存在未確認缺漏平日"


def test_missing_stock_day_blocks_outcome():
    data,signal=_sample(missing_stock=(70,0))
    r=research_integrity(data,signal,signal)
    assert r.iloc[0]["判定"]=="個股在觀察期間缺少行情"


def test_large_unadjusted_move_requires_review():
    data,signal=_sample(spike=True)
    r=research_integrity(data,signal,signal)
    assert "疑似公司行動" in r.iloc[0]["判定"]


def test_bounded_research_loader():
    engine=create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as cx:
        cx.execute(prices.insert().values(day="2025-01-02",market="TWSE",code="1111",name="X",
               open=10,high=10,low=10,close=10,volume=100,amount=1000,source="test"))
    assert len(load_prices_between(engine,date(2025,1,1),date(2025,1,3)))==1
    with pytest.raises(ValueError):
        load_prices_between(engine,date(2024,1,1),date(2025,1,3))
