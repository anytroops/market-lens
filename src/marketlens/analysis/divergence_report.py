"""Phase 4 orchestration: verified pairs -> aligned spreads -> tables and figures.

Kalshi daily prices follow the same quote rule as calibration: last trade
when the day traded, else bid/ask midpoint when the closing spread is at
most 0.20, else no observation for that day.
"""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from marketlens.analysis import divergence as dv

log = logging.getLogger(__name__)

MAX_QUOTE_SPREAD = 0.20
EVENT_THRESHOLD = 5.0


def load_daily_prices(conn: sqlite3.Connection, platform: str,
                      ids: set[str]) -> dict[str, pd.Series]:
    """Daily price series per market id, using the shared quote rule."""
    series: dict[str, list[tuple[int, float]]] = defaultdict(list)
    q = ",".join("?" * len(ids))
    for mid, ts, price, bid, ask in conn.execute(
            f"SELECT market_id, ts, price, bid, ask FROM prices "
            f"WHERE platform = ? AND market_id IN ({q})",
            [platform, *ids]):
        if price is None:
            if bid is None or ask is None or (ask - bid) > MAX_QUOTE_SPREAD:
                continue
            price = (bid + ask) / 2.0
        series[mid].append((ts, price))
    out = {}
    for mid, points in series.items():
        points.sort()
        out[mid] = dv.daily_series(
            np.array([p[0] for p in points]),
            np.array([p[1] for p in points]))
    return out


def build_pair_table(conn: sqlite3.Connection) -> pd.DataFrame:
    """Per-pair spread statistics for all verified pairs with enough overlap."""
    pairs = conn.execute(
        """SELECT m.polymarket_id, m.kalshi_id, m.orientation, m.basis_risk,
                  pm.title, k.title, k.category, pm.volume, k.close_ts
           FROM matches m
           JOIN markets pm ON pm.platform='polymarket' AND pm.market_id=m.polymarket_id
           JOIN markets k ON k.platform='kalshi' AND k.market_id=m.kalshi_id
           WHERE m.human_verified = 1""").fetchall()
    pm_prices = load_daily_prices(conn, "polymarket", {p[0] for p in pairs})
    k_prices = load_daily_prices(conn, "kalshi", {p[1] for p in pairs})

    rows = []
    for (pm_id, k_id, orientation, basis_risk, pm_title, k_title,
         category, volume, close_ts) in pairs:
        pm_s, k_s = pm_prices.get(pm_id), k_prices.get(k_id)
        if pm_s is None or k_s is None:
            continue
        df = dv.align_pair(pm_s, k_s, orientation or "same")
        st = dv.spread_stats(df["spread"])
        if st is None or st.n_days < 2:
            continue
        events = dv.half_life_events(df["spread"], EVENT_THRESHOLD)
        rows.append({
            "pm_id": pm_id, "kalshi_id": k_id, "orientation": orientation,
            "basis_risk": basis_risk, "category": category,
            "pm_title": pm_title, "k_title": k_title, "volume": volume,
            "close_ts": close_ts, "n_days": st.n_days,
            "mean_abs": st.mean_abs, "max_abs": st.max_abs,
            "pct_gt2": st.pct_gt2, "pct_gt5": st.pct_gt5,
            "pct_gt10": st.pct_gt10,
            "n_events_resolved": len(events),
            "half_lives": events,
        })
    return pd.DataFrame(rows)


def aggregate_summary(table: pd.DataFrame) -> dict:
    """Headline numbers across pairs, weighting each pair-day equally."""
    total_days = int(table["n_days"].sum())
    w = table["n_days"] / total_days
    all_hl = [h for hs in table["half_lives"] for h in hs]
    return {
        "pairs": int(len(table)),
        "pair_days": total_days,
        "mean_abs_spread": float((table["mean_abs"] * w).sum()),
        "pct_days_gt2": float((table["pct_gt2"] * w).sum()),
        "pct_days_gt5": float((table["pct_gt5"] * w).sum()),
        "pct_days_gt10": float((table["pct_gt10"] * w).sum()),
        "n_divergence_events_resolved": len(all_hl),
        "median_half_life_days": float(np.median(all_hl)) if all_hl else None,
        "p75_half_life_days": float(np.percentile(all_hl, 75)) if all_hl else None,
    }
