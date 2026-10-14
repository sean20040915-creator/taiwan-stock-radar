"""Official daily snapshot adapters. No invented prices or unsupported backfill.

Only 4-digit Taiwan security codes (excluding 91xx TDR) are preliminarily kept.
This is NOT a complete verified common-stock master; stronger security-type and
listing-condition checks are required before any production trading decisions.
"""
from __future__ import annotations
import math
import re
from datetime import date
import requests

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TWStockRadarResearch/3.0)", "Accept": "application/json"}


def parse_day(value: str) -> str:
    raw = re.sub(r"\D", "", str(value))
    if len(raw) == 7:
        y, m, d = int(raw[:3]) + 1911, int(raw[3:5]), int(raw[5:7])
    elif len(raw) == 8:
        y, m, d = int(raw[:4]), int(raw[4:6]), int(raw[6:8])
    else:
        raise ValueError(f"Unknown trading day: {value!r}")
    return date(y, m, d).isoformat()


def num(value):
    raw = re.sub(r"<[^>]*>", "", str(value)).strip().replace(",", "")
    if raw in {"", "--", "-", "---", "N/A", "null", "nan", "—"}:
        return None
    try:
        n = float(raw)
        return n if math.isfinite(n) else None
    except ValueError:
        return None


def valid_code(value):
    code = str(value).strip()
    return bool(re.fullmatch(r"[1-9][0-9]{3}", code)) and not code.startswith("91")


def _get(row, *keys):
    for key in keys:
        if key in row:
            return row[key]
    raise KeyError(f"Missing keys {keys}")


def parse_snapshot(rows, market: str) -> list[dict]:
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{market}: empty or non-list response")
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            if market == "TWSE":
                code, name = row["Code"], row["Name"]
                values = [row[k] for k in ["OpeningPrice", "HighestPrice", "LowestPrice", "ClosingPrice", "TradeVolume", "TradeValue"]]
            elif market == "TPEX":
                code, name = row["SecuritiesCompanyCode"], row["CompanyName"]
                values = [row[k] for k in ["Open", "High", "Low", "Close", "TradingShares", "TransactionAmount"]]
            else:
                raise ValueError(f"Unknown market {market}")
            if not valid_code(code):
                continue
            values = list(map(num, values))
            if any(v is None for v in values):
                continue
            op, hi, lo, close, volume, amount = values
            if not (0 < lo <= op <= hi and lo <= close <= hi and volume > 0 and amount > 0):
                continue
            day = parse_day(row["Date"])
            items.append({"day": day, "market": market, "code": str(code).strip(),
                          "name": str(name).strip(), "open": op, "high": hi, "low": lo,
                          "close": close, "volume": volume, "amount": amount,
                          "source": TWSE_URL if market == "TWSE" else TPEX_URL})
        except (ValueError, KeyError, TypeError):
            continue
    if len(items) < 100:
        raise ValueError(f"{market}: only {len(items)} usable rows; API schema may have changed")
    days = {x["day"] for x in items}
    if len(days) != 1:
        raise ValueError(f"{market}: mixed trading dates {days}")
    if len({x["code"] for x in items}) != len(items):
        raise ValueError(f"{market}: duplicated codes")
    return items


def fetch_snapshot(market: str, timeout=30) -> list[dict]:
    url = {"TWSE": TWSE_URL, "TPEX": TPEX_URL}[market]
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    return parse_snapshot(response.json(), market)
