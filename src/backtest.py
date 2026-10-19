"""Daily-bar technical-ONLY example backtest; NOT the complete SOP.

Candidate close t; trigger close t+1 or t+2; entry next session OPEN.
A five-session maximum includes the entry session. Within one daily bar,
stop wins whenever both stop/target touched. Gaps are filled at open,
not wished-away at stop. Slippage and taxes/fees are explicit assumptions.
"""
import numpy as np
import pandas as pd
from .strategy import scored_frame
from .diagnostics import assess_entry, resolve_exit


def simulate(prices: pd.DataFrame, cash=1_000_000.0, fee=.001425, tax=.003,
             slippage=.001, max_holding=5, risk_pct=.005, position_pct=.15, scored=None) -> pd.DataFrame:
    d = scored if scored is not None else scored_frame(prices)
    trades = []
    if d.empty:
        return pd.DataFrame()
    for (market, code), g in d.groupby(["market", "code"]):
        g = g.sort_values("day").reset_index(drop=True)
        i = 0
        while i < len(g) - 1:
            signal = g.iloc[i]
            if not bool(signal.trigger):
                i += 1
                continue
            entry_row = g.iloc[i+1]
            decision = assess_entry(signal, entry_row, cash=cash, slippage=slippage,
                                    risk_pct=risk_pct, position_pct=position_pct)
            if decision["code"] != "OK":
                i += 1
                continue
            resolved = resolve_exit(g, i+1, stop=decision["stop"],
                                    target=decision["target"], max_holding=max_holding)
            if resolved is None:
                i += 1
                continue
            exit_idx, exit_reason, raw_exit = resolved
            entry, qty = decision["entry"], decision["qty"]
            received = raw_exit * (1-slippage)
            gross_buy = qty * entry
            gross_sell = qty * received
            net = gross_sell * (1-fee-tax) - gross_buy * (1+fee)
            trades.append({"市場":market,"代號":code,"名稱":signal["name"],
                "突破日":str(signal.day),"進場日":str(entry_row.day),
                "出場日":str(g.iloc[exit_idx].day),"進場價":round(entry,3),
                "停損價":round(decision["stop"],3),"目標價":round(decision["target"],3),
                "賣出價":round(received,3),"股數":qty,"出場原因":exit_reason,
                "淨損益":round(net,2),"淨報酬率":net/gross_buy,
                "淨R倍數":net/(gross_buy*decision["risk"])})
            i = exit_idx + 1
    return pd.DataFrame(trades)

def metrics(trades: pd.DataFrame):
    if trades.empty:
        return {"交易數":0,"淨勝率":None,"平均淨R":None,"總淨損益":0,"獲利因子":None,"最大回撤（逐筆近似）":None}
    pnl = trades["淨損益"].astype(float)
    profit = float(pnl[pnl>0].sum())
    loss = float(-pnl[pnl<0].sum())
    ordered = trades.sort_values(["出場日","代號"])
    equity = ordered["淨損益"].cumsum()
    peak = equity.cummax().clip(lower=0)
    dd = (equity-peak).min()
    return {"交易數":len(trades), "淨勝率":float((pnl>0).mean()),
            "平均淨R":float(trades["淨R倍數"].mean()),"總淨損益":float(pnl.sum()),
            "獲利因子":profit/loss if loss else None,
            "最大回撤（逐筆近似）":float(dd)}


def signal_outcomes(prices: pd.DataFrame, scored=None) -> pd.DataFrame:
    """Setup signal t -> highest close? REQUIRE high, from t+1 through t+5.
    Does NOT imply an executable trade/return.
    """
    d = scored if scored is not None else scored_frame(prices)
    result = []
    for (market,code),g in d.groupby(["market","code"]):
        g=g.reset_index(drop=True)
        for i in range(len(g)-5):
            r=g.iloc[i]
            if not r.setup:
                continue
            future=g.iloc[i+1:i+6]
            best = future.high.max()/r.close-1
            result.append({"訊號日":r.day,"市場":market,"代號":code,
                "名稱":r["name"],"技術分":int(r.score),
                "後5日最高相對漲幅":float(best),"曾達7%":bool(best>=.07)})
    return pd.DataFrame(result)
