"""Daily-bar technical-ONLY example backtest; NOT the complete SOP.

Candidate close t; trigger close t+1 or t+2; entry next session OPEN.
A five-session maximum includes the entry session. Within one daily bar,
stop wins whenever both stop/target touched. Gaps are filled at open,
not wished-away at stop. Slippage and taxes/fees are explicit assumptions.
"""
import numpy as np
import pandas as pd
from .strategy import scored_frame


def simulate(prices: pd.DataFrame, cash=1_000_000.0, fee=.001425, tax=.003,
             slippage=.001, max_holding=5, risk_pct=.005, position_pct=.15, scored=None) -> pd.DataFrame:
    d = scored if scored is not None else scored_frame(prices)
    trades = []
    if d.empty:
        return pd.DataFrame()
    for (market, code), g in d.groupby(["market","code"]):
        g = g.reset_index(drop=True)
        i = 0
        while i < len(g)-1:
            r = g.iloc[i]
            if not r.trigger:
                i += 1
                continue
            entry_row = g.iloc[i+1]
            # Gaps beyond 2% prohibit chasing.
            if entry_row.open > r.close*1.02 or not np.isfinite(r.atr14):
                i += 1
                continue
            entry = float(entry_row.open) * (1+slippage)
            stop = min(float(r.low5_prev), entry-float(r.atr14))
            risk = (entry-stop)/entry
            if not .02 <= risk <= .045:
                i += 1
                continue
            target = entry*(1+max(.07,2*risk))
            lots = int(min(cash*risk_pct/(entry-stop),cash*position_pct/entry)//1000)
            if lots < 1:
                i += 1
                continue
            qty = lots*1000
            last = min(i+max_holding,len(g)-1)
            exit_idx = last
            exit_reason, raw_exit = "第5日時間出場", float(g.iloc[last].close)
            for j in range(i+1,last+1):
                bar = g.iloc[j]
                # if a gap crosses stop, cannot fill at a fictional stop price
                if bar.open<=stop:
                    exit_idx,exit_reason,raw_exit=j,"跳空停損",float(bar.open)
                    break
                if bar.low<=stop:
                    exit_idx,exit_reason,raw_exit=j,"停損優先",stop
                    break
                if bar.open>=target:
                    exit_idx,exit_reason,raw_exit=j,"跳空停利",float(bar.open)
                    break
                if bar.high>=target:
                    exit_idx,exit_reason,raw_exit=j,"目標停利",target
                    break
            received = raw_exit*(1-slippage)
            gross_buy = qty*entry
            gross_sell = qty*received
            net = gross_sell*(1-fee-tax)-gross_buy*(1+fee)
            net_pct = net/gross_buy
            trades.append({"市場":market,"代號":code,"名稱":r["name"],
                "突破日":str(r.day),"進場日":str(entry_row.day),
                "出場日":str(g.iloc[exit_idx].day),"進場價":round(entry,3),
                "停損價":round(stop,3),"目標價":round(target,3),
                "賣出價":round(received,3),"股數":qty,"出場原因":exit_reason,
                "淨損益":round(net,2),"淨報酬率":net_pct,"淨R倍數":net/(gross_buy*risk)})
            # Do not create overlapping per-symbol trades while the position is open.
            i = exit_idx+1
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
