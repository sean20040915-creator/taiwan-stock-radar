"""Lightweight database-level archive extent summary (no full history load)."""
from __future__ import annotations
import pandas as pd
from sqlalchemy import select, func, distinct
from .storage import prices


def archive_coverage(engine) -> pd.DataFrame:
    """Count distinct stored market days, not verified exchange sessions."""
    statement = (select(
        prices.c.market.label("市場"),
        func.min(prices.c.day).label("最早資料日"),
        func.max(prices.c.day).label("最新資料日"),
        func.count(distinct(prices.c.day)).label("已保存市場日數"),
        func.count().label("價格筆數"),
        func.count(distinct(prices.c.code)).label("出現過的代號數"),
    ).group_by(prices.c.market).order_by(prices.c.market))
    with engine.connect() as cx:
        return pd.read_sql(statement, cx)
