"""Matching orchestration: DB -> matcher -> matches table + verification CSV."""

from __future__ import annotations

import csv
import datetime as dt
import logging
import sqlite3
from pathlib import Path

from marketlens.matching import matcher

log = logging.getLogger(__name__)


def _load_inputs(conn: sqlite3.Connection, platform: str,
                 since: str, until: str) -> list[matcher.MatchInput]:
    rows = conn.execute(
        """SELECT market_id, title, raw_json, close_ts, category
           FROM headline_markets
           WHERE platform = ? AND close_ts >= ? AND close_ts < ?""",
        (platform, since, until)).fetchall()
    out = []
    for market_id, title, raw_json, close_ts, category in rows:
        text = title
        series = None
        if platform == "kalshi":
            text = matcher.kalshi_match_text(title, raw_json)
            series = market_id.split("-")[0]
        out.append(matcher.MatchInput(
            market_id=market_id,
            text=matcher.normalize_title(text),
            close_date=dt.date.fromisoformat(close_ts[:10]),
            bucket=matcher.category_bucket(platform, category),
            series=series,
        ))
    return out


def run_matching(conn: sqlite3.Connection, since: str, until: str,
                 threshold: float, window_days: int,
                 csv_path: Path) -> dict:
    """Generate candidates, store them in matches, emit verification CSV."""
    pm = _load_inputs(conn, "polymarket", since, until)
    k = _load_inputs(conn, "kalshi", since, until)
    log.info("matching %d polymarket vs %d kalshi markets", len(pm), len(k))

    candidates = matcher.build_candidates(pm, k, threshold, window_days)
    log.info("%d mutual-best candidates at threshold %s", len(candidates), threshold)

    method = f"token_set_ratio+blocking(w{window_days}d,t{threshold:g})"
    # Regenerating candidates replaces prior UNVERIFIED rows; human-verified
    # rows are never deleted by automation.
    conn.execute("DELETE FROM matches WHERE human_verified = 0")
    conn.executemany(
        """INSERT INTO matches (polymarket_id, kalshi_id, method, score, human_verified)
           VALUES (?, ?, ?, ?, 0)
           ON CONFLICT (polymarket_id, kalshi_id) DO UPDATE SET
               method = excluded.method, score = excluded.score""",
        [(c.polymarket_id, c.kalshi_id, method, c.score) for c in candidates],
    )
    conn.commit()

    priced = {p: {r[0] for r in conn.execute(
        "SELECT DISTINCT market_id FROM prices WHERE platform = ?", (p,))}
        for p in ("polymarket", "kalshi")}
    import json as _json

    meta = {}
    for platform in ("polymarket", "kalshi"):
        for mid, title, close_ts, cat, vol, raw in conn.execute(
                """SELECT market_id, title, close_ts, category, volume, raw_json
                   FROM markets WHERE platform = ?""", (platform,)):
            sub, url = "", ""
            try:
                parsed = _json.loads(raw)
                if platform == "kalshi":
                    sub = str(parsed.get("yes_sub_title") or "")
                else:
                    slug = parsed.get("slug")
                    url = f"https://polymarket.com/market/{slug}" if slug else ""
            except (TypeError, ValueError):
                pass
            meta[(platform, mid)] = (title, close_ts, cat, vol, sub, url)

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "score", "pm_id", "pm_title", "pm_close", "pm_category", "pm_volume",
            "kalshi_id", "kalshi_title", "kalshi_subtitle", "kalshi_close",
            "kalshi_category", "kalshi_volume", "both_have_prices", "pm_url",
            "verified",
        ])
        for c in candidates:
            pm_meta = meta[("polymarket", c.polymarket_id)]
            k_meta = meta[("kalshi", c.kalshi_id)]
            both_priced = (c.polymarket_id in priced["polymarket"]
                           and c.kalshi_id in priced["kalshi"])
            w.writerow([
                f"{c.score:.1f}", c.polymarket_id, pm_meta[0], pm_meta[1],
                pm_meta[2], pm_meta[3], c.kalshi_id, k_meta[0], k_meta[4],
                k_meta[1], k_meta[2], k_meta[3], int(both_priced), pm_meta[5], "",
            ])

    n_priced = sum(
        1 for c in candidates
        if c.polymarket_id in priced["polymarket"] and c.kalshi_id in priced["kalshi"])
    return {"pm_markets": len(pm), "kalshi_markets": len(k),
            "candidates": len(candidates), "both_priced": n_priced}
