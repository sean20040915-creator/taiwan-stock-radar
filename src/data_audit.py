"""V3.5 read-only historical EOD quality audit.

This is a *coverage inventory*, NOT a certified exchange trading calendar.
Missing weekday rows may be unregistered holidays, outages or pending backfill.
No synthetic prices, auto-fixing, order signals or dividend adjustments.
"""
from __future__ import annotations

from datetime import date
import pandas as pd
from sqlalchemy import select, func, case, or_
from .storage import prices
from .market_calendar import is_known_market_closure

ARCHIVE_START = date(2024, 10, 21)
ARCHIVE_END = date(2026, 10, 19)
MARKETS = ("TWSE", "TPEX")

DETAIL_COLS = [
    "市場", "日期", "狀態", "行情筆數", "異常OHLCV筆數", "參考典型筆數",
]
SUMMARY_COLS = [
    "市場", "候選交易平日", "已有行情平日", "未確認缺漏平日",
    "已登記休市平日", "異常交易日", "資料存在率(%)", "資料品質狀態",
]


def read_daily_counts(engine, start=ARCHIVE_START, end=ARCHIVE_END) -> pd.DataFrame:
    """Group in SQL to avoid downloading millions of OHLCV rows to Streamlit."""
    if start > end:
        raise ValueError("Invalid archive date range")
    c = prices.c
    bad = or_(
        c.open.is_(None), c.high.is_(None), c.low.is_(None),
        c.close.is_(None), c.volume.is_(None), c.amount.is_(None),
        c.low <= 0, c.high < c.low,
        c.open < c.low, c.open > c.high,
        c.close < c.low, c.close > c.high,
        c.volume <= 0, c.amount <= 0,
    )
    stmt = (
        select(
            c.market.label("市場"), c.day.label("日期"),
            func.count().label("行情筆數"),
            func.sum(case((bad, 1), else_=0)).label("異常OHLCV筆數"),
        )
        .where(c.day >= start.isoformat(), c.day <= end.isoformat())
        .group_by(c.market, c.day)
        .order_by(c.market, c.day)
    )
    with engine.connect() as connection:
        return pd.read_sql(stmt, connection)


def analyze_archive_coverage(
    daily_counts: pd.DataFrame, start=ARCHIVE_START, end=ARCHIVE_END,
    thin_fraction=.60, min_typical_rows=100,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Status per market/weekday; never equate weekday with verified session."""
    if start > end:
        raise ValueError("Archive end must not precede start")
    if not 0 < thin_fraction < 1:
        raise ValueError("thin_fraction must be between zero and one")
    required = {"市場", "日期", "行情筆數", "異常OHLCV筆數"}
    if not required.issubset(daily_counts.columns):
        raise ValueError(f"Missing daily columns: {sorted(required - set(daily_counts.columns))}")
    counts = daily_counts.copy()
    if not counts.empty:
        counts["日期"] = pd.to_datetime(counts["日期"], errors="raise").dt.date
        if counts.duplicated(["市場", "日期"]).any():
            raise ValueError("Duplicate market/day aggregate detected")
        if (~counts["市場"].isin(MARKETS)).any():
            raise ValueError("Unknown market in archive daily aggregates")
        counts["行情筆數"] = pd.to_numeric(counts["行情筆數"], errors="raise")
        counts["異常OHLCV筆數"] = pd.to_numeric(counts["異常OHLCV筆數"], errors="raise")
    lookups = {(r["市場"], r["日期"]): r for r in counts.to_dict("records")}
    weekdays = [x.date() for x in pd.date_range(start, end, freq="B")]
    details, summaries = [], []
    for market in MARKETS:
        valid_counts = [
            int(row["行情筆數"])
            for (m, day), row in lookups.items()
            if m == market and start <= day <= end
            and day.weekday() < 5 and not is_known_market_closure(market, day)
            and int(row["行情筆數"]) >= min_typical_rows
        ]
        typical = int(pd.Series(valid_counts).median()) if valid_counts else None
        present = missing = holidays = anomalous = 0
        for day in weekdays:
            record = lookups.get((market, day))
            n = int(record["行情筆數"]) if record else 0
            bad = int(record["異常OHLCV筆數"]) if record else 0
            closed = is_known_market_closure(market, day)
            if closed:
                holidays += 1
                status = "休市日卻有行情（待核實）" if n else "已登記休市"
            elif not record:
                missing += 1
                status = "缺資料／未登記休市（待核實）"
            else:
                present += 1
                if bad > 0:
                    status = "OHLCV異常（待核實）"
                elif typical is not None and n < max(min_typical_rows, typical * thin_fraction):
                    status = "股票筆數偏少（待核實）"
                else:
                    status = "有行情（尚未認證完整）"
            if "待核實" in status and record is not None:
                anomalous += 1
            details.append({
                "市場": market, "日期": day.isoformat(), "狀態": status,
                "行情筆數": n, "異常OHLCV筆數": bad,
                "參考典型筆數": typical,
            })
        expected = len(weekdays) - holidays
        rate = (100 * present / expected) if expected else None
        summaries.append({
            "市場": market, "候選交易平日": expected,
            "已有行情平日": present, "未確認缺漏平日": missing,
            "已登記休市平日": holidays, "異常交易日": anomalous,
            "資料存在率(%)": round(rate, 2) if rate is not None else None,
            "資料品質狀態": (
                "需排查缺漏／異常" if missing or anomalous else
                "初步有資料；仍需官方交易日曆與公司行動核對"
            ),
        })
    return (pd.DataFrame(summaries, columns=SUMMARY_COLS),
            pd.DataFrame(details, columns=DETAIL_COLS))


def backtest_data_gate(summary: pd.DataFrame) -> tuple[bool, str]:
    """Strict research gate: date gaps and anomalies block certified 3/5-day claims.

    Even full coverage is not validation: delistings, adjustment, security
    classification, execution, and independent OOS still remain unresolved.
    """
    if summary.empty:
        return False, "尚無可核實的行情覆蓋摘要"
    if int(summary["未確認缺漏平日"].sum()) > 0:
        return False, "存在尚未補齊或尚未確認休市的平日，不能認定歷史第3／5日對齊正確"
    if int(summary["異常交易日"].sum()) > 0:
        return False, "存在異常行情日，需核對原始來源"
    return False, "資料日期初步完整；但除權息、歷史下市股、證券類別與樣本外成交驗證尚未完成"
