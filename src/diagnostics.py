"""V3.2 diagnostic-only audit for technical triggers and research backtests.

The rules here are shared by the backtest and its diagnostic report. No model
validation, stock recommendation, or look-ahead claims are implied.
"""
from __future__ import annotations

import math
import pandas as pd


DIAGNOSTIC_COLUMNS = [
    "突破日", "市場", "代號", "名稱", "技術分", "次日", "次日開盤",
    "跳空幅度", "停損距離", "模擬股數", "判定", "已完成交易", "說明",
]
OUTCOME_COLUMNS = [
    "訊號日", "市場", "代號", "名稱", "訊號類型", "技術分",
    "第3日收盤變動", "第5日收盤變動", "後5日最高價變動", "曾觸及7%",
]


def assess_entry(signal, next_bar, *, cash=1_000_000.0,
                 slippage=.001, risk_pct=.005, position_pct=.15):
    """One deterministic entry-rule decision, using signal and next-day OPEN only."""
    if next_bar is None:
        return {"code": "WAIT_NEXT", "reason": "等待突破後下一交易日開盤行情"}
    opening, signal_close = float(next_bar["open"]), float(signal["close"])
    gap = opening / signal_close - 1
    context = {"next_day": str(next_bar["day"]), "open": opening, "gap": gap}
    if opening > signal_close * 1.02:
        return dict(context, code="GAP", reason="次日跳空超過2%，取消追價")
    if not pd.notna(signal["atr14"]) or not math.isfinite(float(signal["atr14"])):
        return dict(context, code="ATR", reason="突破訊號的ATR14資料不足")
    if not pd.notna(signal["low5_prev"]):
        return dict(context, code="STOP_DATA", reason="前5日低點資料不足")
    entry = opening * (1 + slippage)
    stop = min(float(signal["low5_prev"]), entry - float(signal["atr14"]))
    risk = (entry - stop) / entry
    if not math.isfinite(risk) or not .02 <= risk <= .045:
        return dict(context, code="RISK", reason="停損距離不在2%～4.5%", risk=risk)
    target = entry * (1 + max(.07, 2 * risk))
    lots = int(min(cash * risk_pct / (entry - stop), cash * position_pct / entry) // 1000)
    if lots < 1:
        return dict(context, code="LOT", reason="研究資金不足以配置一張（1000股）", risk=risk)
    return dict(context, code="OK", reason="通過全部模擬進場門檻", entry=entry,
                stop=stop, risk=risk, target=target, qty=lots * 1000)


def resolve_exit(group: pd.DataFrame, entry_idx: int, *, stop: float,
                 target: float, max_holding=5):
    """Exit only after a known stop/target or a complete five-session window.

    None means that the trade remains open at the end of available history.
    Entry day counts as day 1. Intraday stop takes precedence over target.
    """
    last = min(entry_idx + max_holding - 1, len(group) - 1)
    for j in range(entry_idx, last + 1):
        bar = group.iloc[j]
        if bar.open <= stop:
            return j, "跳空停損", float(bar.open)
        if bar.low <= stop:
            return j, "停損優先", float(stop)
        if bar.open >= target:
            return j, "跳空停利", float(bar.open)
        if bar.high >= target:
            return j, "目標停利", float(target)
    if last < entry_idx + max_holding - 1:
        return None  # never fabricate a last-day close / completed trade
    return last, "第5日時間出場", float(group.iloc[last].close)


def diagnose_triggers(scored: pd.DataFrame, *, cash=1_000_000.0,
                      slippage=.001, risk_pct=.005, position_pct=.15,
                      max_holding=5) -> pd.DataFrame:
    """Explain all trigger-to-trade dropouts, including unavailable future bars.

    An earlier completed trade blocks later same-symbol signals until its exit.
    """
    if scored.empty:
        return pd.DataFrame(columns=DIAGNOSTIC_COLUMNS)
    records = []
    for (market, code), group in scored.groupby(["market", "code"], sort=True):
        group = group.sort_values("day").reset_index(drop=True)
        blocked_until = -1
        for i in range(len(group)):
            signal = group.iloc[i]
            if not bool(signal.trigger):
                continue
            row = {"突破日": str(signal.day), "市場": market, "代號": code,
                   "名稱": str(signal["name"]), "技術分": int(signal.score),
                   "次日": None, "次日開盤": None, "跳空幅度": None,
                   "停損距離": None, "模擬股數": None,
                   "判定": None, "已完成交易": False, "說明": None}
            if i <= blocked_until:
                row.update(判定="重疊訊號", 說明="前筆交易仍在持有期內，回測不重複開倉")
                records.append(row)
                continue
            next_bar = group.iloc[i+1] if i+1 < len(group) else None
            decision = assess_entry(signal, next_bar, cash=cash,
                                    slippage=slippage, risk_pct=risk_pct,
                                    position_pct=position_pct)
            row.update(次日=decision.get("next_day"), 次日開盤=decision.get("open"),
                       跳空幅度=decision.get("gap"), 停損距離=decision.get("risk"),
                       模擬股數=decision.get("qty"), 說明=decision["reason"])
            if decision["code"] != "OK":
                row["判定"] = {"WAIT_NEXT": "等待次日行情", "GAP": "跳空超過2%",
                             "ATR": "ATR缺漏", "STOP_DATA": "停損資料缺漏",
                             "RISK": "停損距離不符", "LOT": "資金不足一張"}[decision["code"]]
            else:
                resolved = resolve_exit(group, i+1, stop=decision["stop"],
                                        target=decision["target"], max_holding=max_holding)
                if resolved is None:
                    row.update(判定="持有期未完成", 說明="已通過進場規則，但未觸發出場且未有完整5個交易日行情")
                else:
                    exit_idx, exit_reason, _ = resolved
                    row.update(判定="已完成模擬交易", 已完成交易=True,
                               說明=f"已完成：{exit_reason}")
                    blocked_until = exit_idx
            records.append(row)
    return pd.DataFrame.from_records(records, columns=DIAGNOSTIC_COLUMNS)


def historical_signal_outcomes(scored: pd.DataFrame) -> pd.DataFrame:
    """Retrospective close-to-close observation of mutually exclusive setup/trigger.

    Future session highs are for analysis only and NEVER executable profits.
    Requires five observed post-signal stock sessions; no forward-fill.
    """
    if scored.empty:
        return pd.DataFrame(columns=OUTCOME_COLUMNS)
    records = []
    for (market, code), group in scored.groupby(["market", "code"], sort=True):
        group = group.sort_values("day").reset_index(drop=True)
        for i in range(len(group) - 5):
            signal = group.iloc[i]
            kind = "突破確認" if bool(signal.trigger) else "蓄勢候選" if bool(signal.setup) else None
            if kind is None:
                continue
            future = group.iloc[i+1:i+6]
            if len(future) != 5 or float(signal.close) <= 0:
                continue
            base = float(signal.close)
            records.append({"訊號日": str(signal.day), "市場": market,
                            "代號": code, "名稱": str(signal["name"]),
                            "訊號類型": kind, "技術分": int(signal.score),
                            "第3日收盤變動": float(future.iloc[2].close) / base - 1,
                            "第5日收盤變動": float(future.iloc[4].close) / base - 1,
                            "後5日最高價變動": float(future.high.max()) / base - 1,
                            "曾觸及7%": bool(float(future.high.max()) / base - 1 >= .07)})
    return pd.DataFrame.from_records(records, columns=OUTCOME_COLUMNS)
