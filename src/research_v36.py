"""V3.6 conservative research audit; never a validated investment backtest."""
from datetime import timedelta
import pandas as pd
from .market_calendar import is_known_market_closure

def research_integrity(scored, start, end, min_market_codes=100, spike_limit=.30):
    columns=["市場","代號","訊號日","訊號類型","技術分","後3日收盤變動(%)","後5日收盤變動(%)","判定"]
    if scored.empty:
        return pd.DataFrame(columns=columns)
    frame=scored.copy()
    frame["day"]=pd.to_datetime(frame.day).dt.date
    # A full-market trading date requires a sizeable contemporaneous population,
    # not merely a single ticker. A missing entire market weekday blocks every
    # horizon spanning it, except an explicitly registered closure.
    markets={}
    start_buffer=start-timedelta(days=130)
    for market,g in frame.groupby("market"):
        counts=g.groupby("day").code.nunique()
        dates=sorted(x for x,n in counts.items() if n>=min_market_codes)
        markets[market]=(dates,set(dates))
    records=[]
    for (market,code),g in frame.groupby(["market","code"],sort=False):
        dates,date_set=markets.get(market,([],set()))
        positions={d:i for i,d in enumerate(dates)}
        g=g.sort_values("day").drop_duplicates("day")
        byday=g.set_index("day")
        for _,r in g.iterrows():
            day=r.day
            if not start<=day<=end or not (bool(r.setup) or bool(r.trigger)):
                continue
            category="突破確認" if bool(r.trigger) else "蓄勢候選"
            row={"市場":market,"代號":str(code),"訊號日":str(day),"訊號類型":category,
                 "技術分":int(r.score),"後3日收盤變動(%)":None,
                 "後5日收盤變動(%)":None,"判定":"待核實"}
            i=positions.get(day)
            if i is None or i<64:
                row["判定"]="市場行情不足65個交易日"
            elif i+5>=len(dates):
                row["判定"]="市場後5個交易日尚未完整"
            else:
                required=dates[i-64:i+6]
                # Never skip a weekday that may be a real trading session.
                missing_weekdays=[x.date() for x in pd.bdate_range(required[0],required[-1])
                                  if x.date() not in date_set and
                                  not is_known_market_closure(market,x.date())]
                if missing_weekdays:
                    row["判定"]="市場存在未確認缺漏平日"
                elif not set(required).issubset(set(g.day)):
                    row["判定"]="個股在觀察期間缺少行情"
                else:
                    sub=byday.loc[required]
                    close=pd.to_numeric(sub.close,errors="coerce")
                    high=pd.to_numeric(sub.high,errors="coerce")
                    low=pd.to_numeric(sub.low,errors="coerce")
                    if close.isna().any() or (close<=0).any() or (high<low).any():
                        row["判定"]="OHLC資料異常"
                    elif close.pct_change(fill_method=None).abs().gt(spike_limit).any():
                        row["判定"]="疑似公司行動或價格跳變，需人工核對"
                    else:
                        row["後3日收盤變動(%)"]=round((float(close.iloc[-3])/float(close.iloc[-6])-1)*100,3)
                        row["後5日收盤變動(%)"]=round((float(close.iloc[-1])/float(close.iloc[-6])-1)*100,3)
                        row["判定"]="僅可描述性觀察（未調整公司行動）"
            records.append(row)
    return pd.DataFrame(records,columns=columns).sort_values(["訊號日","市場","代號"])


def research_readiness(prices, start, end, min_market_codes=100, pre_days=135, post_days=15):
    """Explain whether a zero-signal research result is interpretable.

    'Candidate sessions' are weekdays excluding *registered* closures; they
    are not a certified exchange calendar. Price-day presence is not a full
    adjusted-security master or survivorship-bias audit.
    """
    first = start - timedelta(days=pre_days)
    last = end + timedelta(days=post_days)
    if end < start:
        raise ValueError("Research window is reversed")
    if prices.empty:
        counts = pd.DataFrame(columns=["market", "day", "n"])
    else:
        d = prices[["day", "market", "code"]].copy()
        d["day"] = pd.to_datetime(d["day"], errors="raise").dt.date
        d = d[(d.day >= first) & (d.day <= last)]
        counts = d.groupby(["market", "day"], as_index=False).agg(n=("code", "nunique"))
    rows = []
    for market in ("TWSE", "TPEX"):
        grouped = counts[counts.market == market]
        present = {r.day for r in grouped.itertuples() if r.n >= min_market_codes}
        def expected(a, b):
            if b < a:
                return []
            return [x.date() for x in pd.bdate_range(a, b)
                    if not is_known_market_closure(market, x.date())]
        before = expected(first, start-timedelta(days=1))
        during = expected(start, end)
        after = expected(end+timedelta(days=1), last)
        observed_before = sum(x in present for x in before)
        observed_during = sum(x in present for x in during)
        observed_after = sum(x in present for x in after)
        missing_before = sum(x not in present for x in before)
        missing_during = sum(x not in present for x in during)
        missing_after = sum(x not in present for x in after)
        if not observed_during:
            verdict = "訊號期間缺乏行情；0訊號無法解讀"
        elif observed_before < 65:
            verdict = "前置行情不足65日；0訊號無法解讀"
        elif observed_after < 5:
            verdict = "後續行情不足5日；無法完整驗證"
        elif missing_during:
            verdict = "訊號期間存在未核實缺口；0訊號無法解讀"
        elif missing_before or missing_after:
            verdict = "前後行情有待核實缺口；不宜推論0訊號"
        else:
            verdict = "日期存在性初步足夠；仍未驗證下市股與除權息"
        rows.append({
            "市場": market, "訊號期應核對平日": len(during),
            "訊號期有行情日": observed_during,
            "訊號期未核實缺口": missing_during,
            "前置有行情日": observed_before,
            "前置未核實缺口": missing_before,
            "後續有行情日": observed_after,
            "後續未核實缺口": missing_after,
            "資料就緒判定": verdict,
        })
    return pd.DataFrame(rows)
