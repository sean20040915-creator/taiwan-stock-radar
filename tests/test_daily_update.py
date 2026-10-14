from datetime import datetime
from zoneinfo import ZoneInfo
from scripts import update as task
from src.storage import make_engine,load_prices,load_runs,load_scans


def make_rows(market):
    day=datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    codes=range(1100,1201) if market=="TWSE" else range(6100,6201)
    return [{"day":day,"market":market,"code":str(i),"name":f"unit-{i}",
             "open":10.,"high":11.,"low":9.,"close":10.,"volume":1_000_000.,
             "amount":10_000_000.,"source":"mock-official-response"} for i in codes]


def test_full_update_without_live_network(tmp_path,monkeypatch):
    url=f"sqlite:///{tmp_path/'pipeline.db'}"
    monkeypatch.setattr(task,"database_url",lambda:url)
    monkeypatch.setattr(task,"fetch_snapshot",make_rows)
    msg=task.update(require_remote=False)
    engine=make_engine(url)
    assert len(load_prices(engine))==202
    assert len(load_scans(engine))==202
    assert load_runs(engine).iloc[0].status=="SUCCESS"
    assert "TWSE" in msg and "TPEX" in msg
    # Idempotent rerun, rows remain 202 rather than doubling.
    task.update(require_remote=False)
    assert len(load_prices(engine))==202
