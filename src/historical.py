"""Cautious historical all-market EOD adapters for research/backfill.

Uses DATE-addressable TWSE MI_INDEX and TPEx market report endpoints (distinct
from the daily OpenAPI latest-snapshot endpoints). These historical page APIs
can change shape or throttle. Invalid/unrecognized data raises, never fabricates.
Not adjusted for dividends/splits; no security-type registry is applied.
"""
from __future__ import annotations
from datetime import date
import re
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import requests
from src.sources import HEADERS, num, valid_code
from src.market_calendar import is_known_market_closure

TWSE_HISTORY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
TPEX_HISTORY_URL = "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php"

class NoSessionData(Exception):
    """Official report says no daily data (possible holiday/market closure)."""


def client() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    retry = Retry(total=3, connect=3, read=3, backoff_factor=1.6,
                  status_forcelist=[429,500,502,503,504,520,522,524], allowed_methods=["GET"],
                  respect_retry_after_header=True)
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def roc(d: date):
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


def _label(s):
    return re.sub(r"\s+|<[^>]+>", "", str(s)).replace("（", "(").replace("）", ")")


def _field_index(fields, choices):
    labels=[_label(f) for f in fields]
    for choice in choices:
        target=_label(choice)
        if target in labels:
            return labels.index(target)
    return None


def _market_table(payload, market):
    tables = payload.get("tables", [])
    if market == "TWSE" and not tables:
        tables=[{"fields":payload.get("fields9",[]), "data":payload.get("data9",[])}]
    if market == "TPEX" and not tables:
        if payload.get("fields") and payload.get("data"):
            tables=[{"fields":payload["fields"],"data":payload["data"]}]
    for t in tables:
        fields=t.get("fields",[])
        if market == "TWSE":
            required=[("證券代號",), ("證券名稱",), ("開盤價",), ("收盤價",), ("成交股數",)]
        else:
            required=[("代號","證券代號"),("名稱","證券名稱"),("開盤","開盤價"),("收盤","收盤價"),("成交股數","成交股數(股)","成交張數")]
        if t.get("data") and all(_field_index(fields,r) is not None for r in required):
            return t
    raise ValueError(f"{market}: expected OHLCV table not found; review upstream schema")


def _extract_date_token(s):
    val=str(s)
    m=re.search(r"(?<!\d)(\d{3,4})\s*[年/\-]\s*(\d{1,2})\s*[月/\-]\s*(\d{1,2})(?:日)?",val)
    if m:
        y=int(m.group(1))
        if y<1911: y+=1911
        try: return date(y,int(m.group(2)),int(m.group(3)))
        except ValueError: return None
    nums=re.sub(r"\D", "",val)
    if len(nums)==8 and nums.startswith("20"):
        try: return date(int(nums[:4]),int(nums[4:6]),int(nums[6:8]))
        except ValueError: return None
    if len(nums)==7:
        try: return date(int(nums[:3])+1911,int(nums[3:5]),int(nums[5:7]))
        except ValueError: return None
    return None


def _checked_payload_date(payload, expected, table=None):
    # Reject a response that clearly belongs to another date, e.g. latest-day
    # quote returned even though the request specified an earlier day.
    candidates=[]
    for k in ("date","reportDate","report_date","Date"):
        if payload.get(k): candidates.append(payload[k])
    if table is not None:
        for k in ("date","title","subtitle"):
            if table.get(k): candidates.append(table[k])
    parsed=[d for val in candidates if (d:=_extract_date_token(val))]
    if parsed and any(d!=expected for d in parsed):
        raise ValueError(f"Report date mismatch: requested {expected}, returned {parsed}")
    # Some official TPEx historical responses omit report-date metadata. In that
    # case the query date is assumed; this uncertainty is documented in source.
    return bool(parsed)


def parse_historical(payload: dict, market: str, expected: date):
    if not isinstance(payload,dict):
        raise ValueError(f"{market}: unexpected payload type")
    # TWSE reports "OK", while the TPEx historical endpoint may return "ok".
    # A successful lower-case status must NEVER be classified as a closed market.
    raw_status = str(payload.get("stat", "")).strip()
    if raw_status and raw_status.casefold() != "ok":
        no_data_markers = ("沒有符合", "查無", "無資料", "no data", "no records")
        if any(marker in raw_status.casefold() for marker in no_data_markers):
            raise NoSessionData(f"{market} {expected}: {raw_status}")
        raise ValueError(f"{market} {expected}: unrecognized upstream status: {raw_status[:100]}")
    if not payload.get("tables") and not payload.get("data9") and not payload.get("data"):
        raise ValueError(f"{market} {expected}: no expected tables/data (upstream schema may have changed)")
    table=_market_table(payload,market)
    _checked_payload_date(payload,expected,table)
    fields=table["fields"]
    specs={
      "code":("證券代號",) if market=="TWSE" else ("代號","證券代號"),
      "name":("證券名稱",) if market=="TWSE" else ("名稱","證券名稱"),
      "open":("開盤價",) if market=="TWSE" else ("開盤","開盤價"),
      "high":("最高價",) if market=="TWSE" else ("最高","最高價"),
      "low":("最低價",) if market=="TWSE" else ("最低","最低價"),
      "close":("收盤價",) if market=="TWSE" else ("收盤","收盤價"),
      "volume":("成交股數",) if market=="TWSE" else ("成交股數","成交股數(股)","成交張數"),
      "amount":("成交金額",) if market=="TWSE" else ("成交金額(元)","成交金額","成交金額(仟元)","成交金額(千元)"),
    }
    indices={k:_field_index(fields, names) for k,names in specs.items()}
    if any(v is None for v in indices.values()):
        raise ValueError(f"{market}: unsupported source field names {fields}")
    vol_header=_label(fields[indices["volume"]]); amount_header=_label(fields[indices["amount"]])
    vol_scale=1000 if "張" in vol_header else 1
    amount_scale=1000 if "千元" in amount_header or "仟元" in amount_header else 1
    records=[]
    for row in table["data"]:
        try:
            code=str(row[indices["code"]]).strip()
            if not valid_code(code): continue
            values={k:num(row[i]) for k,i in indices.items() if k not in ("code","name")}
            if any(v is None for v in values.values()): continue
            op,hi,lo,close=(values[k] for k in ("open","high","low","close"))
            volume=values["volume"]*vol_scale
            amount=values["amount"]*amount_scale
            if not (0 < lo <= op <= hi and lo <= close <= hi and volume>0 and amount>0): continue
            records.append(dict(day=expected.isoformat(),market=market,code=code,
                name=str(row[indices["name"]]).strip(),open=op,high=hi,low=lo,
                close=close,volume=volume,amount=amount,
                source=(TWSE_HISTORY_URL if market=="TWSE" else TPEX_HISTORY_URL)))
        except (IndexError,KeyError,ValueError,TypeError):
            continue
    if len(records)<100:
        raise ValueError(f"{market} {expected}: only {len(records)} valid rows (suspicious)")
    if len(set(r["code"] for r in records)) != len(records):
        raise ValueError(f"{market} {expected}: duplicate codes in response")
    return records


def fetch_historical_day(session:requests.Session, market:str, trading_day:date):
    
    if is_known_market_closure(market, trading_day):
        raise NoSessionData(
            f"{market} {trading_day}: official market holiday"
        )

    if market=="TWSE":
        url=TWSE_HISTORY_URL
        params={"date":trading_day.strftime("%Y%m%d"),"type":"ALLBUT0999","response":"json"}
    elif market=="TPEX":
        url=TPEX_HISTORY_URL
        params={"l":"zh-tw","d":roc(trading_day),"se":"EW","o":"json"}
    else: raise ValueError(f"Unexpected market: {market}")
    r=session.get(url,params=params,timeout=45)
    r.raise_for_status()
    return parse_historical(r.json(),market,trading_day)
