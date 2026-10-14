import pandas as pd
from src.demo import synthetic_prices
from src.strategy import scored_frame, latest_scans
from src.backtest import simulate, signal_outcomes, metrics


def test_finite_scores_and_65_day_warmup():
    d=scored_frame(synthetic_prices())
    assert d.score.between(0,57).all()
    assert d.score_max.eq(57).all()
    assert d.loc[d.bars<65,"setup"].eq(False).all()
    assert len(latest_scans(d))==6


def test_no_lookahead_first_90_days_unchanged():
    prices=synthetic_prices()
    first=scored_frame(prices.groupby("code",group_keys=False).head(90))
    full=scored_frame(prices)
    joined=first.merge(full,on=["day","market","code"],suffixes=("_prefix","_full"))
    assert (joined.score_prefix==joined.score_full).all()
    assert (joined.setup_prefix==joined.setup_full).all()
    assert (joined.trigger_prefix==joined.trigger_full).all()


def test_backtest_smoke():
    d=synthetic_prices()
    trades=simulate(d)
    assert isinstance(trades,pd.DataFrame)
    assert metrics(trades)["交易數"]==len(trades)
    signals=signal_outcomes(d)
    assert isinstance(signals,pd.DataFrame)


def test_never_leak_incomplete_signal_forward():
    data=synthetic_prices()
    first=signal_outcomes(data)
    lastday=data.day.max()
    if not first.empty:
        assert first["訊號日"].max()<lastday


def test_latest_market_scan_excludes_stale_stock():
    src=synthetic_prices()
    old=src[(src.code=="D001")&(src.day==src.day.max())].index
    src=src.drop(index=old)
    latest=latest_scans(scored_frame(src))
    assert "D001" not in set(latest.code)
