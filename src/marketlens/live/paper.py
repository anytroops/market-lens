"""Paper trading: the forward test the backtest cannot be.

For each currently-open matched pair, this evaluates the same entry rule
the historical backtest used, but prices both legs off live executable
depth instead of a flat slippage assumption, and records the signal
without placing anything. No orders, no credentials, no money.

The point is the comparison it makes possible. Every signal stores three
things side by side:

- `touch_edge`: the edge using best bid/ask, which is what the backtest
  effectively saw
- `exec_edge_N`: the edge after actually walking the book for $N
- whether $N was fillable at all

The gap between the first two, measured forward out of sample, is the
honest answer to "does the backtested edge survive real execution?".
Settlement later attaches the realised outcome so per-signal P&L can be
compared against what was predicted at signal time.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass

from marketlens.analysis.backtest import taker_fee
from marketlens.analysis.backtest_report import KALSHI_FEE, PM_FEE_BY_BUCKET
from marketlens.live import books
from marketlens.matching.matcher import category_bucket

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_signals (
    signal_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            INTEGER NOT NULL,
    polymarket_id TEXT NOT NULL,
    kalshi_id     TEXT NOT NULL,
    direction     TEXT NOT NULL,     -- pm_yes | k_yes
    touch_cost    REAL NOT NULL,     -- all-in cost using best bid/ask
    touch_edge    REAL NOT NULL,
    exec_cost_50  REAL, exec_edge_50  REAL,
    exec_cost_200 REAL, exec_edge_200 REAL,
    exec_cost_1000 REAL, exec_edge_1000 REAL,
    pm_best_ask   REAL, k_best_ask REAL,
    pm_best_bid   REAL, k_best_bid REAL,
    settled       INTEGER NOT NULL DEFAULT 0,
    pm_outcome    TEXT,
    kalshi_outcome TEXT,
    realized_payout REAL,
    UNIQUE (polymarket_id, kalshi_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_paper_ts ON paper_signals (ts);
"""

SIZES = (50.0, 200.0, 1000.0)


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


@dataclass(frozen=True)
class PairQuote:
    """All-in cost of locking $1, for one direction, at a given size."""
    direction: str
    cost: float | None       # None when either leg could not be filled
    edge: float | None


def _all_in(yes_price: float | None, no_price: float | None,
            yes_fee_rate: float, no_fee_rate: float) -> float | None:
    """Cost of $1 of guaranteed payout including both taker fees."""
    if yes_price is None or no_price is None:
        return None
    return (yes_price + taker_fee(yes_fee_rate, yes_price)
            + no_price + taker_fee(no_fee_rate, no_price))


def price_pair(pm_book: books.Book, k_book: books.Book, pm_fee: float,
               notional: float | None = None) -> PairQuote:
    """Cheapest direction to lock $1, at the touch or at a given size.

    notional=None prices the touch (best bid/ask), which is the
    backtest's view. A number walks the book for that many dollars per
    leg, which is what a real order would pay.
    """
    if notional is None:
        pm_yes, k_yes = pm_book.best_ask, k_book.best_ask
        pm_no = (1.0 - pm_book.best_bid) if pm_book.best_bid is not None else None
        k_no = (1.0 - k_book.best_bid) if k_book.best_bid is not None else None
    else:
        pm_yes = books.executable_cost(pm_book, notional)
        k_yes = books.executable_cost(k_book, notional)
        pm_no = books.executable_no_cost(pm_book, notional)
        k_no = books.executable_no_cost(k_book, notional)

    a = _all_in(pm_yes, k_no, pm_fee, KALSHI_FEE)      # buy PM yes + Kalshi no
    b = _all_in(k_yes, pm_no, KALSHI_FEE, pm_fee)      # buy Kalshi yes + PM no

    best, direction = None, "pm_yes"
    if a is not None:
        best, direction = a, "pm_yes"
    if b is not None and (best is None or b < best):
        best, direction = b, "k_yes"
    return PairQuote(direction, best, (1.0 - best) if best is not None else None)


def evaluate(pm_book: books.Book, k_book: books.Book,
             pm_category: str | None) -> dict:
    """Full signal record for one pair: touch view plus each size."""
    pm_fee = PM_FEE_BY_BUCKET.get(
        category_bucket("polymarket", pm_category), 0.05)
    touch = price_pair(pm_book, k_book, pm_fee, None)
    out = {
        "direction": touch.direction,
        "touch_cost": touch.cost,
        "touch_edge": touch.edge,
        "pm_best_ask": pm_book.best_ask, "k_best_ask": k_book.best_ask,
        "pm_best_bid": pm_book.best_bid, "k_best_bid": k_book.best_bid,
    }
    for size in SIZES:
        q = price_pair(pm_book, k_book, pm_fee, size)
        out[f"exec_cost_{int(size)}"] = q.cost
        out[f"exec_edge_{int(size)}"] = q.edge
    return out


def record(conn: sqlite3.Connection, pm_id: str, k_id: str, sig: dict,
           ts: int | None = None) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO paper_signals
           (ts, polymarket_id, kalshi_id, direction, touch_cost, touch_edge,
            exec_cost_50, exec_edge_50, exec_cost_200, exec_edge_200,
            exec_cost_1000, exec_edge_1000, pm_best_ask, k_best_ask,
            pm_best_bid, k_best_bid)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ts or int(time.time()), pm_id, k_id, sig["direction"],
         sig["touch_cost"], sig["touch_edge"],
         sig["exec_cost_50"], sig["exec_edge_50"],
         sig["exec_cost_200"], sig["exec_edge_200"],
         sig["exec_cost_1000"], sig["exec_edge_1000"],
         sig["pm_best_ask"], sig["k_best_ask"],
         sig["pm_best_bid"], sig["k_best_bid"]))
    conn.commit()


def settle(conn: sqlite3.Connection) -> int:
    """Attach realised outcomes to signals whose markets have since resolved.

    Payout is $1 when the two legs resolved consistently, which is what a
    correctly matched pair guarantees, and $0 or $2 when they did not.
    """
    rows = conn.execute(
        """SELECT s.signal_id, s.direction, pm.outcome, k.outcome
           FROM paper_signals s
           JOIN markets pm ON pm.platform='polymarket' AND pm.market_id=s.polymarket_id
           JOIN markets k  ON k.platform='kalshi'      AND k.market_id=s.kalshi_id
           WHERE s.settled = 0 AND pm.outcome IS NOT NULL AND k.outcome IS NOT NULL"""
    ).fetchall()
    n = 0
    for sid, direction, pm_out, k_out in rows:
        if direction == "pm_yes":
            payout = float(pm_out == "YES") + float(k_out == "NO")
        else:
            payout = float(k_out == "YES") + float(pm_out == "NO")
        conn.execute(
            """UPDATE paper_signals SET settled=1, pm_outcome=?, kalshi_outcome=?,
               realized_payout=? WHERE signal_id=?""",
            (pm_out, k_out, payout, sid))
        n += 1
    conn.commit()
    return n
