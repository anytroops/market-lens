"""Live order book capture.

Records depth snapshots for currently-open markets so that the question
the historical backtest could not answer becomes answerable: when the
displayed edge was 3 cents, how many dollars could actually have been
filled at that price?

Read-only. This module holds no credentials and places no orders.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3
import time
from dataclasses import dataclass

from marketlens.config import Config
from marketlens.ingest.base import BaseClient
from marketlens.live import books

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS book_snapshots (
    platform    TEXT NOT NULL,
    market_id   TEXT NOT NULL,
    ts          INTEGER NOT NULL,       -- unix seconds of capture
    best_bid    REAL,
    best_ask    REAL,
    -- executable VWAP to buy YES for a given notional, NULL when the
    -- book cannot absorb that size at all
    vwap_50     REAL,
    vwap_200    REAL,
    vwap_1000   REAL,
    depth_bid   REAL,                   -- total dollars resting on the bid
    depth_ask   REAL,
    raw_json    TEXT NOT NULL,
    PRIMARY KEY (platform, market_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_books_ts ON book_snapshots (ts);
"""

SIZES = (50.0, 200.0, 1000.0)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


@dataclass
class Snapshot:
    platform: str
    market_id: str
    ts: int
    book: books.Book
    raw: dict

    def row(self) -> tuple:
        vwaps = [books.executable_cost(self.book, s) for s in SIZES]
        depth_bid = sum(l.price * l.size for l in self.book.bids)
        depth_ask = sum(l.price * l.size for l in self.book.asks)
        return (self.platform, self.market_id, self.ts,
                self.book.best_bid, self.book.best_ask, *vwaps,
                depth_bid, depth_ask,
                json.dumps(self.raw, separators=(",", ":")))


def store(conn: sqlite3.Connection, snaps: list[Snapshot]) -> int:
    conn.executemany(
        """INSERT INTO book_snapshots
           (platform, market_id, ts, best_bid, best_ask, vwap_50, vwap_200,
            vwap_1000, depth_bid, depth_ask, raw_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (platform, market_id, ts) DO NOTHING""",
        [s.row() for s in snaps])
    conn.commit()
    return len(snaps)


class LiveBookClient:
    """Fetches live depth from both venues through the shared polite client."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.kalshi = BaseClient("kalshi_live", cfg.kalshi.base_url,
                                 cfg.http, cfg.raw_dir())
        self.clob = BaseClient("polymarket_live", cfg.polymarket.clob_base_url,
                               cfg.http, cfg.raw_dir())
        self.gamma = BaseClient("polymarket_live", cfg.polymarket.gamma_base_url,
                                cfg.http, cfg.raw_dir())

    def close(self) -> None:
        for c in (self.kalshi, self.clob, self.gamma):
            c.close()

    def kalshi_book(self, ticker: str, depth: int = 20) -> Snapshot | None:
        # cache=False: a cached order book is a contradiction in terms.
        payload = self.kalshi.get_json(f"/markets/{ticker}/orderbook",
                                       {"depth": depth}, cache=False)
        book = books.parse_kalshi_book(payload)
        if not book.bids and not book.asks:
            return None
        return Snapshot("kalshi", ticker, int(time.time()), book, payload)

    def polymarket_book(self, token_id: str, market_id: str) -> Snapshot | None:
        payload = self.clob.get_json("/book", {"token_id": token_id},
                                     cache=False)
        book = books.parse_polymarket_book(payload)
        if not book.bids and not book.asks:
            return None
        return Snapshot("polymarket", market_id, int(time.time()), book, payload)

    def open_kalshi_markets(self, series: str, limit: int = 200) -> list[dict]:
        page = self.kalshi.get_json("/markets", {
            "series_ticker": series, "status": "open", "limit": limit},
            cache=False)
        return page.get("markets") or []

    def open_polymarket_markets(self, min_volume: float, horizon_days: int = 30,
                                max_pages: int = 20) -> list[dict]:
        """Open Polymarket markets closing within the horizon.

        Sorting by volume instead returns the long-dated 2028 election
        book, which can never match Kalshi's near-dated open markets, so
        the window is set by close date and paged with the keyset
        endpoint (plain limit is capped at 100).
        """
        today = dt.date.today()
        out: list[dict] = []
        cursor = None
        for _ in range(max_pages):
            params = {
                "closed": "false", "active": "true",
                "volume_num_min": min_volume,
                "end_date_min": today.isoformat(),
                "end_date_max": (today + dt.timedelta(days=horizon_days)).isoformat(),
                "include_tag": "true",
                "limit": self.cfg.polymarket.page_size,
            }
            if cursor:
                params["after_cursor"] = cursor
            page = self.gamma.get_json("/markets/keyset", params, cache=False)
            markets = page.get("markets") or []
            out.extend(markets)
            cursor = page.get("next_cursor")
            if not cursor or not markets:
                break
        return out

    def series_categories(self) -> dict[str, str]:
        """Series ticker to category, needed so live markets get real buckets."""
        payload = self.kalshi.get_json("/series", {"limit": 20000}, cache=False)
        return {s["ticker"]: s.get("category")
                for s in payload.get("series") or []}
