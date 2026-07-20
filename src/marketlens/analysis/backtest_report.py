"""Phase 5 orchestration: verified pairs -> fee-adjusted backtest -> tables.

Only same-proposition pairs enter (basis_risk = 0): the strategy's $1
guaranteed payout requires identical resolution. Kalshi legs use the day's
closing bid/ask directly (no midpoints); Polymarket legs use last price
plus the slippage haircut under study.
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from collections import defaultdict

import numpy as np
import pandas as pd

from marketlens.analysis import backtest as bt
from marketlens.analysis.calibration import strip_placeholder_prefix
from marketlens.analysis.divergence import daily_series
from marketlens.matching.matcher import category_bucket

log = logging.getLogger(__name__)

# Polymarket taker fee by coarse category bucket, from config fee schedule
# (crypto 0.07, sports 0.05, finance/politics/tech 0.04, geopolitics 0,
# default 0.05). Buckets follow matcher.category_bucket.
PM_FEE_BY_BUCKET = {
    "crypto": 0.07, "sports": 0.05, "econ": 0.04, "politics": 0.04,
    "science": 0.04, "mentions": 0.04, "entertainment": 0.05,
    "weather": 0.05, "other": 0.05,
}
KALSHI_FEE = 0.07


def _kalshi_quote_frames(conn: sqlite3.Connection,
                         ids: set[str]) -> dict[str, pd.DataFrame]:
    """Daily closing yes bid/ask per Kalshi market."""
    rows = defaultdict(list)
    q = ",".join("?" * len(ids))
    for mid, ts, bid, ask in conn.execute(
            f"SELECT market_id, ts, bid, ask FROM prices "
            f"WHERE platform='kalshi' AND market_id IN ({q})", list(ids)):
        if bid is None or ask is None:
            continue
        rows[mid].append((ts, bid, ask))
    out = {}
    for mid, pts in rows.items():
        pts.sort()
        ts = np.array([p[0] for p in pts])
        bid = daily_series(ts, np.array([p[1] for p in pts]))
        ask = daily_series(ts, np.array([p[2] for p in pts]))
        out[mid] = pd.concat({"k_bid": bid, "k_ask": ask}, axis=1)
    return out


def _pm_price_series(conn: sqlite3.Connection,
                     ids: set[str]) -> dict[str, pd.Series]:
    rows = defaultdict(list)
    q = ",".join("?" * len(ids))
    for mid, ts, price in conn.execute(
            f"SELECT market_id, ts, price FROM prices "
            f"WHERE platform='polymarket' AND market_id IN ({q})", list(ids)):
        if price is not None:
            rows[mid].append((ts, price))
    out = {}
    for mid, pts in rows.items():
        pts.sort()
        ts, px = strip_placeholder_prefix(
            np.array([p[0] for p in pts]), np.array([p[1] for p in pts]))
        if len(ts):
            out[mid] = daily_series(ts, px)
    return out


def run_backtest(conn: sqlite3.Connection, slippage_points: float,
                 edge_threshold: float = 0.0) -> pd.DataFrame:
    """One backtest pass; returns the trades table."""
    pairs = conn.execute(
        """SELECT m.polymarket_id, m.kalshi_id, m.orientation,
                  pm.outcome, k.outcome, pm.category, k.close_ts, pm.title
           FROM matches m
           JOIN markets pm ON pm.platform='polymarket' AND pm.market_id=m.polymarket_id
           JOIN markets k ON k.platform='kalshi' AND k.market_id=m.kalshi_id
           WHERE m.human_verified = 1 AND m.basis_risk = 0""").fetchall()
    pm_prices = _pm_price_series(conn, {p[0] for p in pairs})
    k_quotes = _kalshi_quote_frames(conn, {p[1] for p in pairs})

    trades = []
    n_tradable = 0
    for (pm_id, k_id, orientation, pm_out, k_out, pm_cat,
         k_close, pm_title) in pairs:
        pm_s, k_q = pm_prices.get(pm_id), k_quotes.get(k_id)
        if pm_s is None or k_q is None or pm_out is None or k_out is None:
            continue
        if orientation == "inverse":
            # Flip the PM series so both sides quote the same proposition
            # as Kalshi's YES; outcomes flip accordingly.
            pm_s = 1.0 - pm_s
            pm_out = "YES" if pm_out == "NO" else "NO"
        days = pd.concat({"pm": pm_s}, axis=1).join(k_q, how="inner").dropna()
        # Entry decisions must precede resolution: drop the close day itself.
        resolve_day = dt.date.fromisoformat(k_close[:10])
        days = days[[d < resolve_day for d in days.index]]
        if days.empty:
            continue
        n_tradable += 1
        fee = PM_FEE_BY_BUCKET.get(
            category_bucket("polymarket", pm_cat), 0.05)
        t = bt.backtest_pair(days, pm_out, k_out, fee, KALSHI_FEE,
                             slippage_points, edge_threshold, resolve_day,
                             pm_id=pm_id, kalshi_id=k_id)
        if t:
            trades.append({**t.__dict__, "pm_title": pm_title})
    log.info("slippage %.1f: %d tradable pairs, %d trades entered",
             slippage_points, n_tradable, len(trades))
    df = pd.DataFrame(trades)
    df.attrs["n_tradable"] = n_tradable
    return df


def summarize(trades: pd.DataFrame, n_tradable: int) -> dict:
    if trades.empty:
        return {"tradable_pairs": n_tradable, "opportunities": 0}
    return {
        "tradable_pairs": n_tradable,
        "opportunities": int(len(trades)),
        "pct_of_pairs": round(100 * len(trades) / n_tradable, 2),
        "mean_edge_cents": round(float(trades["edge"].mean()) * 100, 2),
        "median_edge_cents": round(float(trades["edge"].median()) * 100, 2),
        "total_theoretical_pnl": round(float(trades["edge"].sum()), 2),
        "total_realized_pnl": round(float(trades["realized_pnl"].sum()), 2),
        "trades_paying_exactly_1": int((trades["realized_payout"] == 1.0).sum()),
        "median_days_held": float(trades["days_held"].median()),
        "median_annualized_pct": round(
            float(trades["annualized"].median()) * 100, 1),
    }
