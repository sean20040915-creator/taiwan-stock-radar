import pandas as pd
from src.diagnostics import diagnose_triggers, historical_signal_outcomes
from src.backtest import simulate


def _sample(count=7):
    rows = []
    for i in range(count):
        rows.append({
            "day": f"2026-09-{i+1:02d}", "market": "TWSE", "code": "1234",
            "name": "測試", "open": 100., "high": 104., "low": 99.,
            "close": 100., "atr14": 3., "low5_prev": 98.,
            "trigger": i == 0, "setup": i == 0, "score": 49,
        })
    return pd.DataFrame(rows)


def test_missing_next_session_not_a_trade():
    data = _sample(1)
    report = diagnose_triggers(data)
    assert report.iloc[0]["判定"] == "等待次日行情"
    assert simulate(data, scored=data).empty


def test_exclusion_reasons_and_no_threshold_relaxation():
    data = _sample()
    data.loc[1, "open"] = 103
    assert diagnose_triggers(data).iloc[0]["判定"] == "跳空超過2%"
    data.loc[1, "open"] = 100
    data.loc[0, "atr14"] = float("nan")
    assert diagnose_triggers(data).iloc[0]["判定"] == "ATR缺漏"
    data.loc[0, "atr14"] = 10
    assert diagnose_triggers(data).iloc[0]["判定"] == "停損距離不符"
    data.loc[0, "atr14"] = 3
    assert diagnose_triggers(data, cash=100_000).iloc[0]["判定"] == "資金不足一張"


def test_complete_and_incomplete_holding_consistent():
    for size in (2, 4, 5, 6, 7):
        data = _sample(size)
        diag = diagnose_triggers(data)
        trades = simulate(data, scored=data)
        assert int(diag["已完成交易"].sum()) == len(trades)
        if size < 6:
            assert diag.iloc[0]["判定"] == "持有期未完成"
        else:
            assert diag.iloc[0]["判定"] == "已完成模擬交易"


def test_stop_precedes_target_when_both_hit():
    data = _sample(2)
    data.loc[1, "low"] = 95
    data.loc[1, "high"] = 112
    trades = simulate(data, scored=data)
    assert len(trades) == 1
    assert trades.iloc[0]["出場原因"] == "停損優先"


def test_no_immature_forward_outcomes():
    assert historical_signal_outcomes(_sample(5)).empty
    report = historical_signal_outcomes(_sample(7))
    assert len(report) == 1
    assert report.iloc[0]["訊號類型"] == "突破確認"
