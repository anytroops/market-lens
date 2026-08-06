"""Orchestration for live capture and paper trading.

Finds currently-open markets on both venues, matches them with the same
blocked fuzzy matcher used on the historical data, then captures depth
and evaluates the entry rule against real books.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import sqlite3

from marketlens.config import Config
from marketlens.ingest import kalshi as km
from marketlens.ingest import polymarket as pm
from marketlens.live import capture, paper
from marketlens.matching import matcher

log = logging.getLogger(__name__)


def _open_polymarket(client: capture.LiveBookClient, min_volume: float,
                     horizon_days: int = 30) -> list[dict]:
    raw = client.open_polymarket_markets(min_volume, horizon_days)
    return raw if isinstance(raw, list) else []


def productive_series(conn: sqlite3.Connection, limit: int = 250) -> list[str]:
    """Kalshi series that have actually produced verified matches before.

    Bulk-paging every open market does not work: the open universe is
    dominated by multivariate combo products, and the first thousands of
    rows are all KXMVE spam that the inclusion policy rejects anyway.
    Polling every series instead would be roughly 12,000 requests.

    Using the historical matches as a prior is both cheaper and better
    targeted: 179 series produced every verified pair in the study, so
    those are the ones worth watching live.
    """
    rows = conn.execute(
        """SELECT substr(kalshi_id, 1, instr(kalshi_id, '-') - 1) AS series,
                  COUNT(*) AS n
           FROM matches WHERE human_verified = 1
           GROUP BY series HAVING series <> ''
           ORDER BY n DESC LIMIT ?""", (limit,)).fetchall()
    return [r[0] for r in rows]


def _open_kalshi(client: capture.LiveBookClient, cfg: Config,
                 series: list[str]) -> list[dict]:
    """Open Kalshi markets for the given series."""
    out = []
    for s in series:
        try:
            out.extend(client.open_kalshi_markets(s))
        except Exception as e:
            log.warning("open-market fetch failed for %s: %s", s, e)
    return out


def match_open_markets(cfg: Config, client: capture.LiveBookClient,
                       conn: sqlite3.Connection, min_volume: float,
                       threshold: float = 85.0, horizon_days: int = 30
                       ) -> list[tuple[dict, dict, float]]:
    """Pair up currently-open markets on the two venues.

    Uses the historical matcher's blocking and compatibility guards, so a
    pair that would have been rejected in the backtest is rejected here
    too.
    """
    pm_markets = _open_polymarket(client, min_volume, horizon_days)
    k_markets = _open_kalshi(client, cfg, productive_series(conn))
    categories = client.series_categories()
    log.info("open markets: %d polymarket, %d kalshi", len(pm_markets),
             len(k_markets))

    pm_inputs, pm_by_id = [], {}
    for m in pm_markets:
        row = pm.parse_market(m)
        if not row.close_ts:
            continue
        pm_by_id[row.market_id] = m
        pm_inputs.append(matcher.MatchInput(
            market_id=row.market_id,
            text=matcher.normalize_title(row.title),
            close_date=dt.date.fromisoformat(row.close_ts[:10]),
            bucket=matcher.category_bucket("polymarket", row.category)))

    k_inputs, k_by_id = [], {}
    for m in k_markets:
        series_ticker = str(m.get("event_ticker", "")).split("-")[0]
        row = km.parse_market(m, categories.get(series_ticker))
        if row is None or not row.close_ts:
            continue
        k_by_id[row.market_id] = m
        text = matcher.kalshi_match_text(row.title, json.dumps(m))
        k_inputs.append(matcher.MatchInput(
            market_id=row.market_id,
            text=matcher.normalize_title(text),
            close_date=dt.date.fromisoformat(row.close_ts[:10]),
            bucket=matcher.category_bucket("kalshi", row.category),
            series=row.market_id.split("-")[0]))

    cands = matcher.build_candidates(pm_inputs, k_inputs, threshold)
    log.info("%d open pairs matched at threshold %s", len(cands), threshold)
    return [(pm_by_id[c.polymarket_id], k_by_id[c.kalshi_id], c.score)
            for c in cands
            if c.polymarket_id in pm_by_id and c.kalshi_id in k_by_id]


def capture_open_books(cfg: Config, client: capture.LiveBookClient,
                       conn: sqlite3.Connection, min_volume: float,
                       horizon_days: int, limit: int) -> dict:
    """Snapshot depth for the most liquid open markets on both venues."""
    out = {"captured_pm": 0, "captured_kalshi": 0}

    pm_markets = _open_polymarket(client, min_volume, horizon_days)
    pm_markets.sort(key=lambda m: float(m.get("volumeNum") or 0), reverse=True)
    for m in pm_markets[:limit]:
        token = pm.clob_token_for_leg(m)
        if not token:
            continue
        try:
            snap = client.polymarket_book(token, str(m["id"]))
        except Exception as e:
            log.warning("pm book failed for %s: %s", m.get("id"), e)
            continue
        if snap:
            capture.store(conn, [snap])
            out["captured_pm"] += 1

    k_markets = _open_kalshi(client, cfg, productive_series(conn, limit=60))
    k_markets.sort(key=lambda m: float(m.get("volume_fp") or 0), reverse=True)
    for m in k_markets[:limit]:
        try:
            snap = client.kalshi_book(m["ticker"])
        except Exception as e:
            log.warning("kalshi book failed for %s: %s", m.get("ticker"), e)
            continue
        if snap:
            capture.store(conn, [snap])
            out["captured_kalshi"] += 1
    return out


def run_once(cfg: Config, conn: sqlite3.Connection, min_volume: float,
             threshold: float, horizon_days: int = 30,
             capture_limit: int = 60) -> dict:
    """One capture and paper-trading sweep over open matched pairs."""
    capture.ensure_schema(conn)
    paper.ensure_schema(conn)
    client = capture.LiveBookClient(cfg)
    stats = {"pairs": 0, "books": 0, "signals": 0, "positive_touch": 0,
             "positive_at_50": 0, "positive_at_200": 0}
    try:
        # Book capture is deliberately independent of matching. The
        # matched-pair opportunity set is seasonal (one World Cup produced
        # a quarter of every verified pair in the study), so on a quiet
        # day there may be nothing to paper trade, but depth data is
        # still worth collecting and is what answers the backtest's
        # central open question about executable size.
        stats.update(capture_open_books(cfg, client, conn, min_volume,
                                        horizon_days, capture_limit))

        pairs = match_open_markets(cfg, client, conn, min_volume,
                                   threshold, horizon_days)
        stats["pairs"] = len(pairs)
        for pm_raw, k_raw, _score in pairs:
            token = pm.clob_token_for_leg(pm_raw)
            if not token:
                continue
            pm_id, k_id = str(pm_raw["id"]), k_raw["ticker"]
            try:
                pm_snap = client.polymarket_book(token, pm_id)
                k_snap = client.kalshi_book(k_id)
            except Exception as e:  # one bad market must not stop the sweep
                log.warning("book fetch failed for %s / %s: %s", pm_id, k_id, e)
                continue
            if pm_snap is None or k_snap is None:
                continue
            capture.store(conn, [pm_snap, k_snap])
            stats["books"] += 2

            sig = paper.evaluate(pm_snap.book, k_snap.book,
                                 pm.derive_category(pm_raw))
            if sig["touch_edge"] is None:
                continue
            paper.record(conn, pm_id, k_id, sig)
            stats["signals"] += 1
            if sig["touch_edge"] > 0:
                stats["positive_touch"] += 1
            if (sig["exec_edge_50"] or -1) > 0:
                stats["positive_at_50"] += 1
            if (sig["exec_edge_200"] or -1) > 0:
                stats["positive_at_200"] += 1
    finally:
        client.close()
    log.info("sweep done: %s", stats)
    return stats
