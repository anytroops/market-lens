"""Idempotent database writers.

Every writer is an upsert keyed on the table's primary key, so re-running
ingestion overwrites rows in place and can never duplicate them.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class MarketRow:
    platform: str
    market_id: str
    title: str
    category: str | None
    open_ts: str | None
    close_ts: str | None
    resolve_ts: str | None
    outcome: str | None
    volume: float | None
    liquidity: float | None
    raw_json: str


@dataclass(frozen=True)
class PriceRow:
    platform: str
    market_id: str
    ts: int
    price: float | None
    bid: float | None
    ask: float | None
    volume: float | None


def upsert_markets(conn: sqlite3.Connection, rows: Iterable[MarketRow]) -> int:
    """Insert or replace market rows. Returns the number of rows written."""
    data = [
        (
            r.platform, r.market_id, r.title, r.category, r.open_ts,
            r.close_ts, r.resolve_ts, r.outcome, r.volume, r.liquidity,
            r.raw_json,
        )
        for r in rows
    ]
    conn.executemany(
        """
        INSERT INTO markets (platform, market_id, title, category, open_ts,
                             close_ts, resolve_ts, outcome, volume, liquidity,
                             raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (platform, market_id) DO UPDATE SET
            title = excluded.title,
            category = excluded.category,
            open_ts = excluded.open_ts,
            close_ts = excluded.close_ts,
            resolve_ts = excluded.resolve_ts,
            outcome = excluded.outcome,
            volume = excluded.volume,
            liquidity = excluded.liquidity,
            raw_json = excluded.raw_json
        """,
        data,
    )
    conn.commit()
    return len(data)


def upsert_prices(conn: sqlite3.Connection, rows: Iterable[PriceRow]) -> int:
    """Insert or replace price rows. Returns the number of rows written."""
    data = [
        (r.platform, r.market_id, r.ts, r.price, r.bid, r.ask, r.volume)
        for r in rows
    ]
    conn.executemany(
        """
        INSERT INTO prices (platform, market_id, ts, price, bid, ask, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (platform, market_id, ts) DO UPDATE SET
            price = excluded.price,
            bid = excluded.bid,
            ask = excluded.ask,
            volume = excluded.volume
        """,
        data,
    )
    conn.commit()
    return len(data)


def markets_with_prices(conn: sqlite3.Connection, platform: str) -> set[str]:
    """Market ids that already have at least one price row (for resumability)."""
    cur = conn.execute(
        "SELECT DISTINCT market_id FROM prices WHERE platform = ?", (platform,)
    )
    return {r[0] for r in cur.fetchall()}
