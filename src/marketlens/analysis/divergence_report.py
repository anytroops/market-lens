"""Phase 4 orchestration: verified pairs -> aligned spreads -> tables and figures.

Daily prices come from the shared rule in analysis/prices.py, which also
discards Kalshi last-trade prints that contradict the same-day book.
"""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from marketlens.analysis import divergence as dv
from marketlens.analysis.calibration import strip_placeholder_prefix
from marketlens.analysis.prices import usable_price

log = logging.getLogger(__name__)

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
        p = usable_price(price, bid, ask)
        if p is None:
            continue
        series[mid].append((ts, p))
    out = {}
    for mid, points in series.items():
        points.sort()
        ts = np.array([p[0] for p in points])
        px = np.array([p[1] for p in points])
        if platform == "polymarket":
            # Drop the pre-first-trade placeholder era (exact 0.5 seeds).
            ts, px = strip_placeholder_prefix(ts, px)
        if len(ts) == 0:
            continue
        out[mid] = dv.daily_series(ts, px)
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


def lead_lag_summary(conn: sqlite3.Connection, min_days: int = 20,
                     max_lag: int = 2) -> dict:
    """Pooled lead-lag correlation of daily price changes across pairs.

    Positive lag k means a Polymarket move today lines up with a Kalshi
    move k days LATER (Polymarket leads). Only pairs with a reasonable
    number of common days contribute, and correlations are averaged
    across pairs so one long pair cannot dominate.
    """
    pairs = conn.execute(
        """SELECT polymarket_id, kalshi_id, orientation FROM matches
           WHERE human_verified = 1""").fetchall()
    pm_prices = load_daily_prices(conn, "polymarket", {p[0] for p in pairs})
    k_prices = load_daily_prices(conn, "kalshi", {p[1] for p in pairs})
    per_lag: dict[int, list[float]] = {l: [] for l in range(-max_lag, max_lag + 1)}
    n_pairs = 0
    for pm_id, k_id, orientation in pairs:
        pm_s, k_s = pm_prices.get(pm_id), k_prices.get(k_id)
        if pm_s is None or k_s is None:
            continue
        df = dv.align_pair(pm_s, k_s, orientation or "same")
        if len(df) < min_days:
            continue
        n_pairs += 1
        for lag, corr in dv.lead_lag_correlation(df, max_lag).items():
            if not np.isnan(corr):
                per_lag[lag].append(corr)
    return {
        "pairs": n_pairs,
        "mean_corr_by_lag": {l: (float(np.mean(v)) if v else None)
                             for l, v in per_lag.items()},
    }


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
