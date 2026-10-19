"""Market-session alignment, non-mature signal and benchmark regression tests."""
import pandas as pd
from src.validation import validation_observations, descriptive_summary


def sample(days=30, missing=None):
    dates = pd.bdate_range("2026-08-03", periods=days)
    rows = []
    for i, day in enumerate(dates):
        for code, rise in (("1001", .01), ("1002", .0)):
            if missing == (code, i):
                continue
            rows.append(dict(day=day.date().isoformat(), market="TWSE", code=code,
                             name="test", close=100 * (1+rise)**i, score=57 if code=="1001" else 40,
                             setup=(code=="1001"), trigger=False, bars=80+i,
                             avg_amount20=100_000_000))
    return pd.DataFrame(rows)


def test_no_missing_stock_market_session_shift():
    data = sample(30, missing=("1001", 3))
    report = validation_observations(data, min_market_bars=1, min_peer_count=1)
    first = report[(report.code=="1001") & (report.day=="2026-08-03")].iloc[0]
    assert first.day3 == "2026-08-06"
    assert pd.isna(first["報酬3日"])
    assert first.day5 == "2026-08-10"
    assert pd.notna(first["報酬5日"])


def test_unmatured_last_days_do_not_count():
    data = sample(30)
    report = validation_observations(data, min_market_bars=1, min_peer_count=1)
    lastday = data.day.max()
    assert (report.loc[report.day==lastday, "5日狀態"]=="等待完整市場5日").all()


def test_equal_weight_market_same_day_baseline_and_score():
    report = validation_observations(sample(30), min_market_bars=1, min_peer_count=2)
    first = report[(report.day=="2026-08-03") & (report.code=="1001")].iloc[0]
    expected = ((1.01**5-1) + 0) / 2
    assert abs(first["基準5日"]-expected) < 1e-10
    assert abs(first["超額5日"]-expected) < 1e-10
    assert first["訊號類型"] == "蓄勢候選"
    assert first["分數區間"] == "50–57"


def test_interval_split_is_descriptive_not_trained():
    report = validation_observations(sample(35), min_market_bars=1, min_peer_count=2)
    assert {"前70%期間", "後30%期間"}.issubset(set(report["期間"]))
    summaries = descriptive_summary(report, "訊號類型")
    assert (summaries["結論"] != "已驗證").all()


def test_insufficient_market_peer_count_prevents_benchmark_claim():
    report = validation_observations(sample(30), min_market_bars=1, min_peer_count=3)
    assert (report["5日狀態"].isin(["同市場基準樣本不足", "等待完整市場5日"])).all()
    assert descriptive_summary(report, "分數區間").empty
