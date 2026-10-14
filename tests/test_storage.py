from datetime import date
from sqlalchemy import create_engine
from src.storage import metadata, store_market_day, load_prices


def test_upsert_per_market_day(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'test.db'}")
    metadata.create_all(engine)
    item=dict(day="2026-10-13",market="TWSE",code="2330",name="台積電",open=100,
             high=101,low=99,close=100,volume=100_000,amount=10_000_000,source="unit-test")
    assert store_market_day(engine,[item])==1
    item["close"]=100.5
    assert store_market_day(engine,[item])==1
    frame=load_prices(engine)
    assert len(frame)==1
    assert frame.iloc[0]["close"]==100.5


def test_partial_import_does_not_erase_other_symbols(tmp_path):
    engine=create_engine(f"sqlite:///{tmp_path/'no_delete.db'}")
    metadata.create_all(engine)
    base=dict(day="2026-10-13",market="TWSE",name="test",open=10,high=11,low=9,
              close=10,volume=2000,amount=20000,source="test")
    store_market_day(engine,[dict(base,code="1101"),dict(base,code="1102")])
    store_market_day(engine,[dict(base,code="1101",close=10.5)])
    data=load_prices(engine)
    assert len(data)==2
    assert data.set_index("code").loc["1101","close"]==10.5
