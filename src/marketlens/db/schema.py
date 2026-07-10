"""SQLite table definitions.

Timestamp conventions:
- markets.open_ts / close_ts / resolve_ts: ISO 8601 UTC text, e.g.
  "2026-06-15T06:04:30Z". Text sorts chronologically and stays readable in SQL.
- prices.ts: integer unix epoch seconds, because price rows are what the
  analysis code does arithmetic on.

Prices convention: all prices are probabilities in [0, 1]. Polymarket rows
have price only (no historical bid/ask exists). Kalshi rows always carry
bid/ask (from candlesticks) and price only on days with actual trades, so
downstream code should use COALESCE(price, (bid + ask) / 2.0).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
    platform    TEXT NOT NULL,          -- 'polymarket' or 'kalshi'
    market_id   TEXT NOT NULL,          -- platform-native id (gamma id / kalshi ticker)
    title       TEXT NOT NULL,
    category    TEXT,
    open_ts     TEXT,                   -- ISO 8601 UTC
    close_ts    TEXT,                   -- ISO 8601 UTC
    resolve_ts  TEXT,                   -- ISO 8601 UTC
    outcome     TEXT,                   -- 'YES' or 'NO'
    volume      REAL,
    liquidity   REAL,
    raw_json    TEXT NOT NULL,
    PRIMARY KEY (platform, market_id)
);

CREATE TABLE IF NOT EXISTS prices (
    platform    TEXT NOT NULL,
    market_id   TEXT NOT NULL,
    ts          INTEGER NOT NULL,       -- unix epoch seconds
    price       REAL,                   -- last-trade probability in [0, 1]
    bid         REAL,
    ask         REAL,
    volume      REAL,
    PRIMARY KEY (platform, market_id, ts)
);

CREATE TABLE IF NOT EXISTS matches (
    match_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    polymarket_id   TEXT NOT NULL,
    kalshi_id       TEXT NOT NULL,
    method          TEXT NOT NULL,
    score           REAL,
    human_verified  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (polymarket_id, kalshi_id)
);

CREATE INDEX IF NOT EXISTS idx_markets_close_ts ON markets (platform, close_ts);
CREATE INDEX IF NOT EXISTS idx_prices_ts ON prices (platform, ts);
"""

# The headline dataset per Sean's inclusion decision (2026-07-09):
# resolved binary markets alive for at least min_lifetime_hours (default 24).
# Encoding the policy as a view keeps it in exactly one place.
HEADLINE_VIEW = """
DROP VIEW IF EXISTS headline_markets;
CREATE VIEW headline_markets AS
SELECT *,
       (julianday(close_ts) - julianday(open_ts)) * 24.0 AS lifetime_hours
FROM markets
WHERE outcome IN ('YES', 'NO')
  AND open_ts IS NOT NULL
  AND close_ts IS NOT NULL
  AND (julianday(close_ts) - julianday(open_ts)) * 24.0 >= {min_lifetime_hours};
"""


def connect(db_path: str | Path, min_lifetime_hours: float = 24.0) -> sqlite3.Connection:
    """Open the database, creating tables and the headline view on first use."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    # Both platforms can ingest concurrently into one database; the busy
    # timeout must be set before any statement that can take locks
    # (journal_mode and DDL below), so it goes first.
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.executescript(HEADLINE_VIEW.format(min_lifetime_hours=float(min_lifetime_hours)))
    return conn
