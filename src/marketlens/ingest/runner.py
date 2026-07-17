"""Ingestion orchestration: clients + parsers -> SQLite, with resume support.

Two stages per platform:
- metadata: page through the platform's resolved-market frame and upsert
  MarketRows. Idempotent by primary key upsert.
- prices: fetch per-market price history for a deterministic uniform random
  sample of headline-eligible markets. Markets that already have price rows
  are skipped, so an interrupted run resumes where it stopped, and the raw
  disk cache makes even re-fetches free.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import random
import sqlite3
from collections import Counter

import httpx

from marketlens.config import Config
from marketlens.db import loaders
from marketlens.ingest import kalshi as km
from marketlens.ingest import polymarket as pm

log = logging.getLogger(__name__)

BATCH_SIZE = 500


def deterministic_sample(ids: list[str], k: int, seed: int) -> list[str]:
    """Uniform random sample of k ids, reproducible for a given seed.

    Ids are sorted first so the result depends only on the set of ids,
    not on database row order.
    """
    ordered = sorted(ids)
    if k >= len(ordered):
        return ordered
    return random.Random(seed).sample(ordered, k)


def _iso_to_epoch(iso_ts: str) -> int:
    return int(dt.datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).timestamp())


def _parse_window(cfg: Config, since: str | None, until: str | None) -> tuple[dt.date, dt.date]:
    return (
        dt.date.fromisoformat(since or cfg.ingestion.since),
        dt.date.fromisoformat(until or cfg.ingestion.until),
    )


def ingest_polymarket_metadata(cfg: Config, conn: sqlite3.Connection,
                               since: str | None = None, until: str | None = None,
                               max_markets: int | None = None) -> Counter:
    d0, d1 = _parse_window(cfg, since, until)
    client = pm.PolymarketClient(cfg)
    stats: Counter = Counter()
    batch: list[loaders.MarketRow] = []
    try:
        for raw in client.iter_closed_markets(d0, d1):
            row = pm.parse_market(raw)
            stats["markets"] += 1
            if row.outcome is None:
                stats["no_clean_outcome"] += 1
            batch.append(row)
            if len(batch) >= BATCH_SIZE:
                loaders.upsert_markets(conn, batch)
                batch = []
                if stats["markets"] % 5000 < BATCH_SIZE:
                    log.info("polymarket metadata: %d markets so far", stats["markets"])
            if max_markets and stats["markets"] >= max_markets:
                break
    finally:
        if batch:
            loaders.upsert_markets(conn, batch)
        client.close()
    log.info("polymarket metadata done: %s", dict(stats))
    return stats


def ingest_kalshi_metadata(cfg: Config, conn: sqlite3.Connection,
                           since: str | None = None, until: str | None = None,
                           max_markets: int | None = None) -> Counter:
    d0, d1 = _parse_window(cfg, since, until)
    client = km.KalshiClient(cfg)
    stats: Counter = Counter()
    try:
        series_list = client.list_series()
        kept = [s for s in series_list if km.keep_series(s, cfg)]
        stats["series_total"] = len(series_list)
        stats["series_kept"] = len(kept)
        log.info("kalshi: %d series, %d kept after skip lists",
                 len(series_list), len(kept))
        categories = {s["ticker"]: s.get("category") for s in kept}
        for i, series in enumerate(kept):
            batch: list[loaders.MarketRow] = []
            for raw in client.iter_settled_markets(series["ticker"], d0, d1):
                row = km.parse_market(raw, categories.get(series["ticker"]))
                if row is None:
                    stats["non_binary_skipped"] += 1
                    continue
                stats["markets"] += 1
                if row.outcome is None:
                    stats["no_clean_outcome"] += 1
                batch.append(row)
                if len(batch) >= BATCH_SIZE:
                    loaders.upsert_markets(conn, batch)
                    batch = []
                if max_markets and stats["markets"] >= max_markets:
                    break
            if batch:
                loaders.upsert_markets(conn, batch)
            if (i + 1) % 500 == 0:
                log.info("kalshi metadata: %d/%d series, %d markets so far",
                         i + 1, len(kept), stats["markets"])
            if max_markets and stats["markets"] >= max_markets:
                break
    finally:
        client.close()
    log.info("kalshi metadata done: %s", dict(stats))
    return stats


def _sampled_headline_ids(cfg: Config, conn: sqlite3.Connection,
                          platform: str) -> list[str]:
    ids = [r[0] for r in conn.execute(
        "SELECT market_id FROM headline_markets WHERE platform = ?", (platform,)
    )]
    sample = deterministic_sample(ids, cfg.ingestion.price_sample_size,
                                  cfg.ingestion.sample_seed)
    log.info("%s: %d headline markets, sampling %d for prices",
             platform, len(ids), len(sample))
    return sample


def ingest_polymarket_prices(cfg: Config, conn: sqlite3.Connection,
                             max_markets: int | None = None,
                             market_ids: list[str] | None = None) -> Counter:
    """Fetch daily price histories. market_ids overrides the random sample
    (used to price specific verified matched pairs on demand)."""
    client = pm.PolymarketClient(cfg)
    stats: Counter = Counter()
    try:
        sample = (sorted(market_ids) if market_ids is not None
                  else _sampled_headline_ids(cfg, conn, pm.PLATFORM))
        if max_markets:
            sample = sample[:max_markets]
        done = loaders.markets_with_prices(conn, pm.PLATFORM)
        for n, market_id in enumerate(sample, 1):
            if market_id in done:
                stats["resumed_skip"] += 1
                continue
            raw = json.loads(conn.execute(
                "SELECT raw_json FROM markets WHERE platform = ? AND market_id = ?",
                (pm.PLATFORM, market_id)).fetchone()[0])
            token = pm.clob_token_for_leg(raw)
            if not token:
                stats["no_token"] += 1
                continue
            try:
                history = client.fetch_price_history(token)
            except (httpx.HTTPStatusError, RuntimeError) as e:
                # Individual markets can vanish upstream; skip, never crash
                # a long run over one market.
                log.warning("price fetch failed for %s: %s", market_id, e)
                stats["fetch_failed"] += 1
                continue
            rows = pm.parse_price_history(history, market_id)
            if rows:
                loaders.upsert_prices(conn, rows)
                stats["markets_with_prices"] += 1
                stats["price_rows"] += len(rows)
            else:
                stats["empty_history"] += 1
            if n % 500 == 0:
                log.info("polymarket prices: %d/%d markets", n, len(sample))
    finally:
        client.close()
    log.info("polymarket prices done: %s", dict(stats))
    return stats


def ingest_kalshi_prices(cfg: Config, conn: sqlite3.Connection,
                         max_markets: int | None = None,
                         market_ids: list[str] | None = None) -> Counter:
    """Fetch daily candlesticks. market_ids overrides the random sample
    (used to price specific verified matched pairs on demand)."""
    client = km.KalshiClient(cfg)
    stats: Counter = Counter()
    try:
        sample = (sorted(market_ids) if market_ids is not None
                  else _sampled_headline_ids(cfg, conn, km.PLATFORM))
        if max_markets:
            sample = sample[:max_markets]
        done = loaders.markets_with_prices(conn, km.PLATFORM)
        for n, market_id in enumerate(sample, 1):
            if market_id in done:
                stats["resumed_skip"] += 1
                continue
            row = conn.execute(
                "SELECT raw_json, open_ts, close_ts FROM markets "
                "WHERE platform = ? AND market_id = ?",
                (km.PLATFORM, market_id)).fetchone()
            raw, open_ts, close_ts = json.loads(row[0]), row[1], row[2]
            if not open_ts or not close_ts:
                stats["missing_window"] += 1
                continue
            try:
                candles = client.fetch_candlesticks(
                    km.series_ticker_of(raw), market_id,
                    _iso_to_epoch(open_ts), _iso_to_epoch(close_ts),
                )
            except (httpx.HTTPStatusError, RuntimeError) as e:
                # Kalshi purges markets on a rolling basis; a market verified
                # last week can 404 today. Count it and move on.
                log.warning("candlesticks failed for %s: %s", market_id, e)
                stats["fetch_failed"] += 1
                continue
            rows = km.parse_candlesticks({"candlesticks": candles}, market_id)
            if rows:
                loaders.upsert_prices(conn, rows)
                stats["markets_with_prices"] += 1
                stats["price_rows"] += len(rows)
            else:
                stats["empty_history"] += 1
            if n % 500 == 0:
                log.info("kalshi prices: %d/%d markets", n, len(sample))
    finally:
        client.close()
    log.info("kalshi prices done: %s", dict(stats))
    return stats
