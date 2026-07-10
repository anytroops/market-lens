"""Phase 3 orchestration: snapshots -> calibration stats -> figures -> results.

Snapshot discipline: a market's forecast at horizon H is its last observed
price at or before (close_ts - H). Only markets whose price history reaches
that far back enter that horizon's sample, so every number is
point-in-time correct (no lookahead).

Kalshi quote handling: a daily candle with no trades carries closing
bid/ask. The snapshot uses the last trade when the candle traded, else the
bid/ask midpoint, but only when the closing spread is at most 0.20
probability points; wider (or empty) books give meaningless midpoints
(an untraded book shows bid 0 / ask 1, midpoint 0.5) and are dropped.
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from collections import defaultdict
from pathlib import Path

import numpy as np

from marketlens.analysis import calibration as cal
from marketlens.matching.matcher import category_bucket
from marketlens.viz import plots

log = logging.getLogger(__name__)

HORIZONS = {"7d": 7 * 86400, "24h": 86400}
MAX_QUOTE_SPREAD = 0.20


def _iso_to_epoch(iso_ts: str) -> int:
    return int(dt.datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).timestamp())


def load_snapshots(conn: sqlite3.Connection, platform: str) -> dict:
    """Per-horizon arrays of (prob, outcome, category bucket, volume)."""
    markets = {
        mid: (close_ts, outcome, category, volume)
        for mid, close_ts, outcome, category, volume in conn.execute(
            """SELECT market_id, close_ts, outcome, category, volume
               FROM headline_markets WHERE platform = ?""", (platform,))
    }
    series: dict[str, list[tuple[int, float]]] = defaultdict(list)
    dropped_wide = 0
    for mid, ts, price, bid, ask in conn.execute(
            "SELECT market_id, ts, price, bid, ask FROM prices WHERE platform = ?",
            (platform,)):
        if price is None:
            if bid is None or ask is None or (ask - bid) > MAX_QUOTE_SPREAD:
                dropped_wide += 1
                continue
            price = (bid + ask) / 2.0
        series[mid].append((ts, price))

    out = {h: {"prob": [], "outcome": [], "bucket": [], "volume": [],
               "market_id": []} for h in HORIZONS}
    for mid, points in series.items():
        meta = markets.get(mid)
        if meta is None:
            continue
        close_ts, outcome, category, volume = meta
        anchor = _iso_to_epoch(close_ts)
        points.sort()
        ts = np.array([p[0] for p in points])
        px = np.array([p[1] for p in points])
        for name, seconds in HORIZONS.items():
            p = cal.price_at_horizon(ts, px, anchor, seconds)
            if p is None:
                continue
            out[name]["prob"].append(p)
            out[name]["outcome"].append(1 if outcome == "YES" else 0)
            out[name]["bucket"].append(category_bucket(platform, category))
            out[name]["volume"].append(volume if volume is not None else 0.0)
            out[name]["market_id"].append(mid)
    for h in out:
        for k in out[h]:
            out[h][k] = np.array(out[h][k])
    log.info("%s: snapshots 7d=%d 24h=%d (dropped %d wide/empty quotes)",
             platform, len(out["7d"]["prob"]), len(out["24h"]["prob"]),
             dropped_wide)
    return out


def longshot_favorite(probs: np.ndarray, outcomes: np.ndarray) -> dict:
    """Effect sizes for the favorite-longshot bias with Wilson CIs."""
    out = {}
    for name, mask in (("longshots (p < 0.10)", probs < 0.10),
                       ("favorites (p > 0.90)", probs > 0.90)):
        n = int(mask.sum())
        if n == 0:
            out[name] = None
            continue
        k = int(outcomes[mask].sum())
        lo, hi = cal.wilson_interval(k, n)
        out[name] = {"n": n, "mean_prob": float(probs[mask].mean()),
                     "yes_rate": k / n, "ci": (lo, hi)}
    return out


def run_analysis(conn: sqlite3.Connection, root: Path) -> str:
    """Compute everything and return the markdown results section."""
    fig_dir = root / "reports" / "figures"
    lines: list[str] = []
    add = lines.append
    summary: dict[str, dict] = {}

    for platform in ("polymarket", "kalshi"):
        snaps = load_snapshots(conn, platform)
        summary[platform] = {}
        for horizon in HORIZONS:
            probs = snaps[horizon]["prob"]
            outs = snaps[horizon]["outcome"]
            if probs.size < 100:
                summary[platform][horizon] = None
                continue
            murphy = cal.murphy_decomposition(probs, outs)
            table = cal.calibration_table(probs, outs)
            flb = longshot_favorite(probs, outs)
            summary[platform][horizon] = {
                "n": int(probs.size), "murphy": murphy, "table": table,
                "flb": flb, "snaps": snaps[horizon],
            }
            plots.reliability_diagram(
                table,
                f"{platform.capitalize()} calibration, {horizon} before close",
                f"n = {probs.size:,} resolved markets, Wilson 95% intervals",
                plots.PALETTE[platform],
                fig_dir / f"calibration_{platform}_{horizon}.png",
            )

    add("# Results")
    add("")
    add("## Calibration (Phase 3)")
    add("")
    add("Forecast = last market price at the stated horizon before close")
    add("(point-in-time, no lookahead). Outcome = 1 when the market's")
    add("proposition resolved YES. Kalshi no-trade candles use the bid/ask")
    add("midpoint when the closing spread is at most 0.20, else the market")
    add("drops out of that horizon's sample.")
    add("")
    add("### Headline table")
    add("")
    add("| Platform | Horizon | N | Brier | Reliability (cal. error) | Resolution | Uncertainty | Base rate |")
    add("|---|---|---|---|---|---|---|---|")
    for platform in ("polymarket", "kalshi"):
        for horizon in HORIZONS:
            s = summary[platform][horizon]
            if s is None:
                add(f"| {platform} | {horizon} | too few markets | | | | | |")
                continue
            m = s["murphy"]
            add(f"| {platform} | {horizon} | {s['n']:,} | {m.brier:.4f} | "
                f"{m.reliability:.4f} | {m.resolution:.4f} | "
                f"{m.uncertainty:.4f} | {m.base_rate:.3f} |")
    add("")
    add("![](figures/calibration_polymarket_7d.png)")
    add("![](figures/calibration_polymarket_24h.png)")
    add("![](figures/calibration_kalshi_7d.png)")
    add("![](figures/calibration_kalshi_24h.png)")
    add("")
    add("### Do markets sharpen as resolution approaches? (paired sample)")
    add("")
    add("Same markets scored at both horizons, so composition cannot")
    add("explain the difference. Sharpening means higher resolution and a")
    add("lower Brier at 24h than at 7d.")
    add("")
    add("| Platform | N (paired) | Brier 7d | Brier 24h | Resolution 7d | Resolution 24h |")
    add("|---|---|---|---|---|---|")
    for platform in ("polymarket", "kalshi"):
        s7, s24 = summary[platform]["7d"], summary[platform]["24h"]
        if s7 is None or s24 is None:
            continue
        ids7 = {m: i for i, m in enumerate(s7["snaps"]["market_id"].tolist())}
        ids24 = {m: i for i, m in enumerate(s24["snaps"]["market_id"].tolist())}
        common = sorted(set(ids7) & set(ids24))
        if len(common) < 100:
            continue
        i7 = [ids7[m] for m in common]
        i24 = [ids24[m] for m in common]
        m7 = cal.murphy_decomposition(
            s7["snaps"]["prob"][i7], s7["snaps"]["outcome"][i7])
        m24 = cal.murphy_decomposition(
            s24["snaps"]["prob"][i24], s24["snaps"]["outcome"][i24])
        add(f"| {platform} | {len(common):,} | {m7.brier:.4f} | {m24.brier:.4f} | "
            f"{m7.resolution:.4f} | {m24.resolution:.4f} |")
    add("")
    add("### Favorite-longshot bias (24h horizon)")
    add("")
    add("| Platform | Segment | N | Mean implied prob | Empirical YES rate | Wilson 95% CI |")
    add("|---|---|---|---|---|---|")
    for platform in ("polymarket", "kalshi"):
        s = summary[platform]["24h"]
        if s is None:
            continue
        for seg, r in s["flb"].items():
            if r is None:
                continue
            add(f"| {platform} | {seg} | {r['n']:,} | {r['mean_prob']:.3f} | "
                f"{r['yes_rate']:.3f} | [{r['ci'][0]:.3f}, {r['ci'][1]:.3f}] |")
    add("")
    add("### Calibration by category (24h horizon, reliability component)")
    add("")
    add("| Platform | Category | N | Brier | Reliability |")
    add("|---|---|---|---|---|")
    for platform in ("polymarket", "kalshi"):
        s = summary[platform]["24h"]
        if s is None:
            continue
        snaps = s["snaps"]
        for bucket in sorted(set(snaps["bucket"].tolist())):
            mask = snaps["bucket"] == bucket
            if mask.sum() < 200:
                continue
            m = cal.murphy_decomposition(snaps["prob"][mask], snaps["outcome"][mask])
            add(f"| {platform} | {bucket} | {int(mask.sum()):,} | "
                f"{m.brier:.4f} | {m.reliability:.4f} |")
    add("")
    add("### Calibration by volume tercile (24h horizon)")
    add("")
    add("| Platform | Tercile | N | Brier | Reliability |")
    add("|---|---|---|---|---|")
    for platform in ("polymarket", "kalshi"):
        s = summary[platform]["24h"]
        if s is None:
            continue
        snaps = s["snaps"]
        vol = snaps["volume"]
        cuts = np.quantile(vol, [1 / 3, 2 / 3])
        names = ["thin", "middle", "deep"]
        tercile = np.digitize(vol, cuts)
        for t in range(3):
            mask = tercile == t
            m = cal.murphy_decomposition(snaps["prob"][mask], snaps["outcome"][mask])
            add(f"| {platform} | {names[t]} | {int(mask.sum()):,} | "
                f"{m.brier:.4f} | {m.reliability:.4f} |")
    add("")
    return "\n".join(lines)
