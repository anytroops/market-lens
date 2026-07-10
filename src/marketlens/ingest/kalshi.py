"""Kalshi ingestion.

Series-first strategy: the /series endpoint returns every series (about
11,300 on 2026-07-09) in one request, including frequency and category.
Series whose markets are sub-24h by construction (fifteen_min, hourly) and
multivariate combo series (KXMVE*, category Exotics) are skipped wholesale;
they account for tens of thousands of settled markets per day that Sean's
inclusion policy excludes anyway. Remaining series are paged one by one via
/markets?series_ticker=... with cursor pagination.

Important quirk found 2026-07-09: filtering by status=settled silently drops
everything settled before roughly December 2025 (older markets report status
'closed' or 'finalized'). So no status filter is sent; resolution is
determined client-side from the result field, which is populated on old
markets too.

Prices come from per-market candlesticks, which include historical
yes_bid/yes_ask OHLC (better than Polymarket, and what makes the Kalshi leg
of the backtest execution-realistic). All prices arrive as dollar strings
in [0, 1]. The "price" OHLC dict is EMPTY on periods with no trades, so
price is nullable and bid/ask carry the quote.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any, Iterator

from marketlens.config import Config
from marketlens.db.loaders import MarketRow, PriceRow
from marketlens.ingest.base import BaseClient
from marketlens.ingest.polymarket import normalize_iso

log = logging.getLogger(__name__)

PLATFORM = "kalshi"

# Candlestick API cap on periods per request, per Kalshi docs.
MAX_PERIODS_PER_REQUEST = 4900


def _dollars(value: Any) -> float | None:
    """Parse Kalshi's dollar-string prices ('0.5800') into floats."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_market(raw: dict, category: str | None) -> MarketRow | None:
    """Normalize one Kalshi market object. Returns None for non-binary markets.

    Category is not on the market object; it comes from the series listing.
    """
    if raw.get("market_type") != "binary":
        return None
    result = raw.get("result")
    outcome = {"yes": "YES", "no": "NO"}.get(result or "")
    volume = _dollars(raw.get("volume_fp"))
    if volume is None:
        volume = raw.get("volume")
    liquidity = _dollars(raw.get("liquidity_dollars"))
    if liquidity is None:
        liquidity = raw.get("liquidity")
    return MarketRow(
        platform=PLATFORM,
        market_id=str(raw["ticker"]),
        title=str(raw.get("title") or ""),
        category=category,
        open_ts=normalize_iso(raw.get("open_time")),
        close_ts=normalize_iso(raw.get("close_time")),
        resolve_ts=normalize_iso(raw.get("settlement_ts"))
        or normalize_iso(raw.get("expiration_time")),
        outcome=outcome,
        volume=volume,
        liquidity=liquidity,
        raw_json=json.dumps(raw, separators=(",", ":")),
    )


def parse_candlesticks(payload: dict, market_id: str) -> list[PriceRow]:
    """Convert a candlesticks response into PriceRows.

    price = last-trade close when the period had trades, else None.
    bid/ask = closing yes_bid/yes_ask, present whenever the book existed.
    """
    rows = []
    for c in payload.get("candlesticks") or []:
        ts = c.get("end_period_ts")
        if ts is None:
            continue
        price = _dollars((c.get("price") or {}).get("close_dollars"))
        bid = _dollars((c.get("yes_bid") or {}).get("close_dollars"))
        ask = _dollars((c.get("yes_ask") or {}).get("close_dollars"))
        volume = _dollars(c.get("volume_fp"))
        if c.get("volume") is not None and volume is None:
            volume = float(c["volume"])
        rows.append(PriceRow(
            platform=PLATFORM, market_id=market_id, ts=int(ts),
            price=price, bid=bid, ask=ask, volume=volume,
        ))
    return rows


def keep_series(series: dict, cfg: Config) -> bool:
    """Inclusion test for a series under the configured skip lists."""
    kcfg = cfg.kalshi
    if series.get("frequency") in kcfg.skip_frequencies:
        return False
    if series.get("category") in kcfg.skip_categories:
        return False
    ticker = series.get("ticker") or ""
    return not any(ticker.startswith(p) for p in kcfg.skip_ticker_prefixes)


class KalshiClient:
    """Fetches Kalshi series, settled markets, and candlestick histories."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.api = BaseClient(PLATFORM, cfg.kalshi.base_url, cfg.http, cfg.raw_dir())

    def close(self) -> None:
        self.api.close()

    def list_series(self) -> list[dict]:
        """All series with ticker, title, category, frequency, tags."""
        payload = self.api.get_json("/series", {"limit": 20000})
        return payload.get("series") or []

    def iter_settled_markets(self, series_ticker: str, since: dt.date,
                             until: dt.date) -> Iterator[dict]:
        """Yield market dicts for one series with close time in the window.

        No status filter: see the module docstring. Callers must check the
        result field to keep only resolved markets.
        """
        t0 = int(dt.datetime.combine(since, dt.time.min, dt.timezone.utc).timestamp())
        t1 = int(dt.datetime.combine(until, dt.time.min, dt.timezone.utc).timestamp())
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {
                "series_ticker": series_ticker,
                "min_close_ts": t0,
                "max_close_ts": t1,
                "limit": self.cfg.kalshi.page_size,
            }
            if cursor:
                params["cursor"] = cursor
            page = self.api.get_json("/markets", params)
            markets = page.get("markets") or []
            yield from markets
            cursor = page.get("cursor")
            if not cursor or not markets:
                return

    def fetch_candlesticks(self, series_ticker: str, market_ticker: str,
                           start_ts: int, end_ts: int) -> list[dict]:
        """Daily candlesticks for one market, chunked under the API's period cap.

        Returns the raw candlestick dicts (already archived to disk page by
        page by the base client).
        """
        period_minutes = self.cfg.ingestion.price_fidelity_minutes
        period_seconds = period_minutes * 60
        chunk_seconds = MAX_PERIODS_PER_REQUEST * period_seconds
        out: list[dict] = []
        t = start_ts
        while t < end_ts:
            t_end = min(t + chunk_seconds, end_ts)
            payload = self.api.get_json(
                f"/series/{series_ticker}/markets/{market_ticker}/candlesticks",
                {"start_ts": t, "end_ts": t_end, "period_interval": period_minutes},
            )
            out.extend(payload.get("candlesticks") or [])
            t = t_end
        return out


def series_ticker_of(market_raw: dict) -> str:
    """Series ticker for a market, derived from its event ticker prefix."""
    event_ticker = str(market_raw.get("event_ticker") or market_raw.get("ticker") or "")
    return event_ticker.split("-")[0]
