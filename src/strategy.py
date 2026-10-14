"""Versioned, deterministic V3 technical-only precursor to SOP V2.

Verified technical dimensions: price/structure 35 + price/volume 12 +
anti-overheat 10 = 57. The other 43 points REQUIRE extra official data.
NEVER rescale technical scores to claim a full 100-point SOP result.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

SCORE_MAX = 57
VERSION = "3.0-tech-mvp"


def indicators(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    required = {"day", "market", "code", "name", "open", "high", "low", "close", "volume", "amount"}
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    df = prices.copy().sort_values(["market", "code", "day"])
    out = []
    for (_, _), g in df.groupby(["market", "code"], sort=False):
        g = g.copy().reset_index(drop=True)
        c, h, l, v, a = [g[x].astype(float) for x in ("close", "high", "low", "volume", "amount")]
        g["bars"] = np.arange(1, len(g)+1)
        g["ma20"] = c.rolling(20, min_periods=20).mean()
        g["ma60"] = c.rolling(60, min_periods=60).mean()
        g["ma20_5ago"] = g["ma20"].shift(5)
        g["prev10high"] = h.shift(1).rolling(10).max()
        g["prev20high"] = h.shift(1).rolling(20).max()
        g["low10"] = l.rolling(10).min()
        g["high10"] = h.rolling(10).max()
        g["range10"] = (g["high10"] - g["low10"]) / g["low10"]
        tr = pd.concat([h-l, (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
        g["atr14"] = tr.rolling(14, min_periods=14).mean()
        g["atr_pct"] = g["atr14"] / c
        g["avgvol20_prev"] = v.shift(1).rolling(20).mean()
        g["avgvol20"] = v.rolling(20).mean()
        g["avgvol5"] = v.rolling(5).mean()
        g["vol_ratio5"] = g["avgvol5"] / g["avgvol20"]
        g["vol_ratio_today"] = v / g["avgvol20_prev"]
        g["avg_amount20"] = a.rolling(20).mean()
        delta = c.diff()
        upvol = v.where(delta > 0, 0).rolling(5).sum()
        downvol = v.where(delta < 0, 0).rolling(5).sum()
        g["updown_vol5"] = upvol / downvol.replace(0, np.nan)
        g["ret1"] = c.pct_change(1)
        g["ret5"] = c.pct_change(5)
        g["ret20"] = c.pct_change(20)
        g["distance20"] = (g["prev20high"] - c) / g["prev20high"]
        g["close_pos"] = (c-l) / (h-l).replace(0,np.nan)
        g["low5_prev"] = l.shift(1).rolling(5).min()
        out.append(g)
    return pd.concat(out, ignore_index=True)


def scored_frame(prices: pd.DataFrame) -> pd.DataFrame:
    d = indicators(prices)
    if d.empty:
        return d
    b = lambda x: x.fillna(False).astype(int)
    d["structure_score"] = (
        10*b((d.close>d.ma20)&(d.ma20>d.ma60)) +
        5*b(d.ma20>d.ma20_5ago) +
        8*b(d.range10<=.12) +
        8*b(d.distance20.between(0,.05,inclusive="both")) +
        4*b(d.atr_pct.between(.02,.06,inclusive="both"))
    )
    d["volume_score"] = (
        6*b(d.vol_ratio5.between(.65,1.30,inclusive="both")) +
        6*b(d.updown_vol5>=1.15)
    )
    d["heat_score"] = 5*b(d.ret5.between(0,.08,inclusive="both")) + 5*b(d.ret20<=.20)
    d["score"] = (d.structure_score+d.volume_score+d.heat_score).astype(int)
    d["score_max"] = SCORE_MAX
    d["hard_pass"] = (
        (d.bars>=65) & (d.avg_amount20>=50_000_000) &
        (d.ret5<=.12) & (d.ret20<=.25) &
        (d.atr_pct.between(.02,.06))
    )
    d["setup"] = d.hard_pass & (d.score>=38) & d.distance20.between(0,.05)
    d["trigger"] = False
    # A setup on either of the two PREVIOUS dates allows a confirmed close breakout today.
    for _, g in d.groupby(["market","code"],sort=False):
        indices = g.index
        prior_setup = g.setup.shift(1,fill_value=False) | g.setup.shift(2,fill_value=False)
        breakout = ((g.close>g.prev10high) & (g.vol_ratio_today>=1.5) &
                    (g.close_pos>=.70) & (g.ret1<=.06) & (g.ret1>-.10) & prior_setup)
        d.loc[indices,"trigger"] = breakout.to_numpy(dtype=bool)
    d["status"] = np.select(
        [d.bars<65, ~d.hard_pass, d.trigger, d.setup],
        ["歷史資料不足", "未過硬性技術門檻", "技術突破已確認", "技術候選／等待突破"],
        default="技術分數未達候選門檻"
    )
    d["reason"] = np.select(
        [d.bars<65, d.avg_amount20<50_000_000, d.ret5>.12,
         d.ret20>.25, ~d.atr_pct.between(.02,.06)],
        ["少於65筆日線資料", "20日均成交金額低於5,000萬元", "5日漲幅過熱", "20日漲幅過熱", "ATR波動率不在2%～6%"],
        default="市場／族群／法人／月營收／公告及處置資料仍未驗證"
    )
    return d


def latest_scans(scored: pd.DataFrame) -> pd.DataFrame:
    if scored.empty:
        return scored.copy()
    # Only keep each market's own latest session; missing/halts must NOT show as current.
    # TWSE and TPEx may legitimately report different latest sessions.
    last = scored.sort_values("day").groupby(["market","code"],sort=False).tail(1).copy()
    latest_per_market=last.groupby("market")["day"].transform("max")
    last=last[last.day.eq(latest_per_market)].copy()
    return last.sort_values(["setup","trigger","score"],ascending=[False,False,False]).reset_index(drop=True)
