"""Simple durable SQLite/PostgreSQL persistence; database is NOT stored in Git."""
from __future__ import annotations
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import pandas as pd
from sqlalchemy import (create_engine, MetaData, Table, Column, String, Float,
                        Integer, Text, PrimaryKeyConstraint, select)

metadata = MetaData()
prices = Table("daily_prices", metadata,
    Column("day", String(10), nullable=False), Column("market", String(8), nullable=False),
    Column("code", String(12), nullable=False), Column("name", String(120)),
    Column("open", Float), Column("high", Float), Column("low", Float), Column("close", Float),
    Column("volume", Float), Column("amount", Float), Column("source", Text),
    PrimaryKeyConstraint("day", "market", "code"))
scans = Table("scan_snapshots", metadata,
    Column("day", String(10), nullable=False), Column("market", String(8), nullable=False),
    Column("code", String(12), nullable=False), Column("name", String(120)),
    Column("score", Integer), Column("score_max", Integer),
    Column("status", String(50)), Column("reason", Text),
    Column("version", String(24), default="3.0-tech-mvp"),
    PrimaryKeyConstraint("day", "market", "code", "version"))
runs = Table("update_runs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("started_at", String(35)), Column("status", String(30)), Column("details", Text))


def database_url():
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg2://" + url[len("postgresql://"):]
        return url
    try:
        import streamlit as st
        url = str(st.secrets.get("DATABASE_URL", "")).strip()
        if url:
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    except (ImportError, FileNotFoundError, KeyError):
        pass
    path = Path(__file__).resolve().parent.parent / "data" / "stocks.sqlite3"
    path.parent.mkdir(exist_ok=True, parents=True)
    return f"sqlite:///{path}"


def make_engine(url=None):
    engine = create_engine(url or database_url(), pool_pre_ping=True)
    metadata.create_all(engine)
    return engine


def _upsert_rows(cx, table, records, key_cols):
    """Chunked idempotent upsert for the two supported database engines.

    Unlike delete+insert, importing a partial CSV NEVER deletes other symbols.
    """
    if not records:
        return
    dialect=cx.dialect.name
    if dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    elif dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        raise ValueError(f"Unsupported DB for upsert: {dialect}")
    for i in range(0,len(records),200):
        batch=records[i:i+200]
        stmt=insert(table).values(batch)
        changed={c.name:getattr(stmt.excluded,c.name) for c in table.c if c.name not in key_cols}
        stmt=stmt.on_conflict_do_update(index_elements=key_cols,set_=changed)
        cx.execute(stmt)


def store_market_day(engine, records):
    if not records:
        return 0
    day, market = records[0]["day"], records[0]["market"]
    if any(x["day"] != day or x["market"] != market for x in records):
        raise ValueError("Mixed day/market batch blocked")
    if len({x["code"] for x in records}) != len(records):
        raise ValueError("Duplicate stock codes blocked")
    with engine.begin() as cx:
        _upsert_rows(cx,prices,records,["day","market","code"])
    return len(records)

def load_prices(engine, lookback_calendar_days=None) -> pd.DataFrame:
    statement=select(prices)
    if lookback_calendar_days is not None:
        cutoff=(datetime.now(ZoneInfo("Asia/Taipei")).date()-timedelta(days=lookback_calendar_days)).isoformat()
        statement=statement.where(prices.c.day>=cutoff)
    with engine.connect() as cx:
        df = pd.read_sql(statement.order_by(prices.c.day, prices.c.market, prices.c.code), cx)
    return df


def save_scan(engine, frame: pd.DataFrame):
    if frame.empty:
        return 0
    wanted = ["day", "market", "code", "name", "score", "score_max", "status", "reason"]
    data = frame[wanted].copy()
    data["version"] = "3.0-tech-mvp"
    records = data.where(pd.notna(data), None).to_dict("records")
    with engine.begin() as cx:
        _upsert_rows(cx,scans,records,["day","market","code","version"])
    return len(records)

def load_scans(engine) -> pd.DataFrame:
    with engine.connect() as cx:
        return pd.read_sql(select(scans).order_by(scans.c.day.desc(), scans.c.score.desc()), cx)


def record_run(engine, started, status, details):
    with engine.begin() as cx:
        cx.execute(runs.insert().values(started_at=started, status=status, details=details[:4000]))


def load_runs(engine) -> pd.DataFrame:
    with engine.connect() as cx:
        return pd.read_sql(select(runs).order_by(runs.c.id.desc()).limit(20), cx)
