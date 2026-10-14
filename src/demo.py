"""Deterministic fictitious sample series; not actual market quotes."""
from datetime import datetime
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd


def synthetic_prices():
    rng = np.random.default_rng(2330)
    end = datetime.now(ZoneInfo("Asia/Taipei")).date()
    days = pd.bdate_range(end=end, periods=126)
    names = ["DEMO-A（虛構）","DEMO-B（虛構）","DEMO-C（虛構）","DEMO-D（虛構）","DEMO-E（虛構）","DEMO-F（虛構）"]
    rows=[]
    for j,name in enumerate(names):
        close=40 + j*17
        for i,day in enumerate(days):
            drift = .0015 if j%2==0 else .0006
            shock = rng.normal(drift,.015+0.002*j)
            if i>105 and j==1: shock += .004
            new=max(5,close*(1+shock))
            op=close*(1+rng.normal(0,.007))
            hi=max(op,new)*(1+rng.uniform(0.001,.011))
            lo=min(op,new)*(1-rng.uniform(0.001,.011))
            volume=float(max(500_000,rng.normal(4_500_000+j*750_000,900_000)))
            # One deliberate fictitious volume-breakout event makes the demo flow observable.
            if j==0 and i==104:
                volume*=1.9
            rows.append({"day":day.date().isoformat(),"market":"DEMO","code":f"D{j+1:03d}",
                "name":name,"open":round(op,3),"high":round(hi,3),"low":round(lo,3),
                "close":round(new,3),"volume":volume,"amount":float(volume*new),"source":"synthetic-fixed-seed"})
            close=new
    return pd.DataFrame(rows)
