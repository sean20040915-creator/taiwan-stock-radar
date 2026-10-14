"""Import verified-history CSV with explicit provenance. Not a data vendor.

python -m scripts.import_csv --file history.csv --source 'paid-provider-name'
CSV columns: day,market,code,name,open,high,low,close,volume,amount
volume = shares, amount = NTD. Updates existing (day,market) slices.
"""
import argparse
from datetime import date
from pathlib import Path
import pandas as pd
from src.sources import valid_code
from src.storage import make_engine, store_market_day

REQUIRED=["day","market","code","name","open","high","low","close","volume","amount"]


def import_history(filename, source):
    if not source or source.lower() in {"unknown","demo","test"}:
        raise ValueError("Provide a verifiable provenance in --source")
    raw=pd.read_csv(filename,dtype={"code":str,"day":str})
    if set(REQUIRED)-set(raw.columns):
        raise ValueError(f"Missing columns: {sorted(set(REQUIRED)-set(raw.columns))}")
    df=raw[REQUIRED].copy()
    if df.empty or len(df)>3_000_000:
        raise ValueError("Empty or oversize CSV")
    df["day"]=pd.to_datetime(df.day,format="%Y-%m-%d",errors="raise").dt.strftime("%Y-%m-%d")
    if df.day.max()>date.today().isoformat():
        raise ValueError("CSV includes dates in the future")
    if not df.market.isin(["TWSE","TPEX"]).all() or not df.code.map(valid_code).all():
        raise ValueError("Market/code invalid; only four-digit TWSE/TPEX equities allowed")
    for col in ["open","high","low","close","volume","amount"]:
        df[col]=pd.to_numeric(df[col],errors="raise")
    if not ((df.low>0)&(df.open>=df.low)&(df.open<=df.high)&
            (df.close>=df.low)&(df.close<=df.high)&(df.volume>0)&(df.amount>0)).all():
        raise ValueError("CSV has invalid price/volume rows")
    if df.duplicated(["day","market","code"]).any():
        raise ValueError("CSV contains duplicate keys")
    df["source"]=source
    eng=make_engine()
    total=0
    for _, batch in df.groupby(["day","market"],sort=True):
        total+=store_market_day(eng,batch.to_dict("records"))
    print(f"Imported {total} rows from {source}. You must verify splits and survivorship bias.")
    return total


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--file",required=True)
    ap.add_argument("--source",required=True)
    args=ap.parse_args()
    import_history(Path(args.file),args.source)
