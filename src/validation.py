"""V3.3 descriptive signal validation against observable same-market daily peers.

NOT a statistically validated strategy. No market index or historical delisted
stocks. Signal-day close is a reference price, NOT an achievable entry. All
forward horizons are anchored to each MARKET's sessions, not each stock's bars.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

COLS = ["day", "market", "code", "name", "score", "分數區間", "訊號類型",
        "期間", "day3", "day5", "報酬3日", "報酬5日",
        "基準3日", "基準5日", "超額3日", "超額5日",
        "同市場基準數5日", "5日狀態"]


def validation_observations(scored: pd.DataFrame, min_market_bars=30,
                            min_peer_count=30) -> pd.DataFrame:
    """Return one stock-session record per as-of-day liquidity-qualified stock.

    Market calendar from dates with >= min_market_bars distinct traded codes.
    Endpoints are exact market session t+3/t+5, no forward filling or next-stock-
    observed-day substitution. Benchmark is equal-weight comparable liquid names
    with complete outcomes in the same market on the same signal day.
    """
    if scored.empty:
        return pd.DataFrame(columns=COLS)
    required = {"day", "market", "code", "name", "close", "score", "setup",
                "trigger", "bars", "avg_amount20"}
    missing = required - set(scored.columns)
    if missing:
        raise ValueError(f"Missing validation columns: {sorted(missing)}")
    d = scored.copy()
    d["day"] = pd.to_datetime(d["day"], errors="raise").dt.normalize()
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    counts = (d.groupby(["market", "day"], as_index=False)
              .agg(n=("code", "nunique")))
    calendar = counts[counts.n >= min_market_bars][["market", "day"]].copy()
    if calendar.empty:
        return pd.DataFrame(columns=COLS)
    calendar = calendar.sort_values(["market", "day"])
    for n in (3, 5):
        calendar[f"day{n}"] = calendar.groupby("market")["day"].shift(-n)
    d = d.merge(calendar, on=["market", "day"], how="inner",
                validate="many_to_one")
    # All benchmarks and score bands use the *same ex-ante* liquidity universe.
    d = d[(d["bars"] >= 65) &
          (pd.to_numeric(d["avg_amount20"], errors="coerce") >= 50_000_000) &
          (d["close"] > 0) & d["score"].between(0, 57)].copy()
    if d.empty:
        return pd.DataFrame(columns=COLS)
    d["分數區間"] = pd.cut(d["score"], bins=[-1, 37, 44, 49, 57],
                           labels=["0–37", "38–44", "45–49", "50–57"]).astype(str)
    d["訊號類型"] = np.select([d["trigger"], d["setup"]],
                              ["突破確認", "蓄勢候選"], default="一般合格股票")
    # Forward data are looked up by (market, code, EXACT future market session).
    # If the stock did not trade that day, the observation stays missing.
    future = scored[["market", "code", "day", "close"]].copy()
    future["day"] = pd.to_datetime(future["day"]).dt.normalize()
    future = future.drop_duplicates(["market", "code", "day"])
    for n in (3, 5):
        right = future.rename(columns={"day": f"futureday{n}",
                                       "close": f"futureclose{n}"})
        d = d.merge(right, left_on=["market", "code", f"day{n}"],
                    right_on=["market", "code", f"futureday{n}"],
                    how="left", validate="many_to_one")
        d[f"報酬{n}日"] = np.where(
            d[f"day{n}"].notna() & (d[f"futureclose{n}"] > 0),
            d[f"futureclose{n}"] / d["close"] - 1, np.nan)
        d = d.drop(columns=[f"futureday{n}", f"futureclose{n}"])
        peers = (d.groupby(["market", "day"], as_index=False)
                 .agg(**{f"基準{n}日": (f"報酬{n}日", "mean"),
                          f"同市場基準數{n}日": (f"報酬{n}日", "count")}))
        d = d.merge(peers, on=["market", "day"], how="left",
                    validate="many_to_one")
        d.loc[d[f"同市場基準數{n}日"] < min_peer_count, f"基準{n}日"] = np.nan
        d[f"超額{n}日"] = d[f"報酬{n}日"] - d[f"基準{n}日"]
    # A chronological partition is descriptive only: the already-designed rules
    # were not trained on the first segment and independently frozen beforehand.
    days = sorted(calendar["day"].unique())
    if len(days) >= 20:
        cut = days[max(1, min(len(days)-1, int(len(days)*.70)))]
        d["期間"] = np.where(d["day"] >= cut, "後30%期間", "前70%期間")
        d.loc[(d["day"] < cut) & (d["day5"] >= cut),
              "期間"] = "切分邊界排除"
    else:
        d["期間"] = "交易日不足20日"
    d["5日狀態"] = np.select(
        [d["day5"].isna(), d["報酬5日"].isna(), d["基準5日"].isna()],
        ["等待完整市場5日", "缺少個股第5日行情", "同市場基準樣本不足"],
        default="完整")
    d["day"] = d["day"].dt.strftime("%Y-%m-%d")
    for n in (3, 5):
        d[f"day{n}"] = d[f"day{n}"].dt.strftime("%Y-%m-%d")
    return d[COLS].sort_values(["day", "market", "code"]).reset_index(drop=True)


def descriptive_summary(records: pd.DataFrame, by: str, min_signals=100,
                        min_independent_dates=20) -> pd.DataFrame:
    """Completed 5-day descriptive outcomes with paired same-market comparators.

    The 'not validated' label is deliberately never upgraded to 'validated':
    missing delistings, adjustments, execution and genuinely untouched periods
    preclude any such claim.
    """
    columns = ["期間", by, "訊號筆數", "不同日期數", "3日平均報酬(%)", "5日平均報酬(%)",
               "5日上漲比例(%)", "5日平均超額(%)", "優於同市場基準比例(%)", "結論"]
    if records.empty:
        return pd.DataFrame(columns=columns)
    if by not in ("分數區間", "訊號類型"):
        raise ValueError("Unsupported summary dimension")
    frame = records[(records["5日狀態"] == "完整") &
                    (records["期間"].isin(["前70%期間", "後30%期間"]))].copy()
    if by == "訊號類型":
        frame = frame[frame["訊號類型"].isin(["蓄勢候選", "突破確認"])]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    data = []
    for (period, label), g in frame.groupby(["期間", by], observed=True):
        n, sessions = len(g), g["day"].nunique()
        data.append({
            "期間": period, by: label, "訊號筆數": n, "不同日期數": sessions,
            "3日平均報酬(%)": round(100 * g["報酬3日"].mean(), 2),
            "5日平均報酬(%)": round(100 * g["報酬5日"].mean(), 2),
            "5日上漲比例(%)": round(100 * (g["報酬5日"] > 0).mean(), 2),
            "5日平均超額(%)": round(100 * g["超額5日"].mean(), 2),
            "優於同市場基準比例(%)": round(100 * (g["超額5日"] > 0).mean(), 2),
            "結論": "描述性樣本不足" if n < min_signals or sessions < min_independent_dates
                    else "描述性數據；策略尚未驗證",
        })
    return pd.DataFrame(data, columns=columns).sort_values(["期間", by]).reset_index(drop=True)
