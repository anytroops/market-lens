"""Polymarket ingestion.

Metadata comes from the Gamma API using the /markets/keyset endpoint
(the plain offset endpoint is capped; the keyset cursor parameter is
after_cursor, verified 2026-07-09). Price histories come from the CLOB API
prices-history endpoint, one request per market, prices already in [0, 1].

Windowing strategy: one keyset stream per calendar day of scheduled end date,
with start_date_max set one day earlier. That last filter is a server-side
approximation of the minimum-lifetime rule which keeps the 15-minute
contracts from ever being downloaded; the exact rule is enforced again
client-side by the headline_markets view.

Leg convention: a Polymarket binary market has two outcomes (usually
Yes/No, sometimes Team A/Team B). We take the "Yes" outcome if present,
otherwise the first outcome, as the market's proposition. The stored
outcome is YES when that leg resolved to 1, and the stored price history
is that leg's CLOB token.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
from typing import Any, Iterator

from marketlens.config import Config
from marketlens.db.loaders import MarketRow, PriceRow
from marketlens.ingest.base import BaseClient

log = logging.getLogger(__name__)

PLATFORM = "polymarket"

# Cosmetic or bulky keys stripped from raw_json stored in the database.
# The complete untouched response remains archived in data/raw/.
_TRIM_KEYS = {
    "image", "icon", "twitterCardImage", "mailchimpTag", "clobRewards",
    "imageOptimized", "iconOptimized",
}
_EVENT_KEEP_KEYS = {"id", "ticker", "slug", "title", "negRisk", "seriesSlug"}


def normalize_iso(value: str | None) -> str | None:
    """Normalize the API's timestamp variants to 'YYYY-MM-DDTHH:MM:SSZ' UTC.

    Handles '2026-06-30T00:00:00Z', '2025-06-19T18:02:51.278733Z',
    and the nonstandard '2026-06-15 06:04:30+00'.
    """
    if not value:
        return None
    s = value.strip().replace(" ", "T")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    d = None
    for candidate in (s, s + ":00"):  # second form completes a bare '+00' offset
        try:
            d = dt.datetime.fromisoformat(candidate)
            break
        except ValueError:
            continue
    if d is None:
        log.warning("unparseable timestamp %r", value)
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json_field(raw: dict, key: str) -> list:
    """Gamma encodes list fields as JSON strings, e.g. outcomes='["Yes","No"]'."""
    v = raw.get(key)
    if v is None:
        return []
    if isinstance(v, list):
        return v
    try:
        parsed = json.loads(v)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def proposition_leg(raw: dict) -> int | None:
    """Index of the outcome treated as the market's proposition.

    'Yes' when present, otherwise the first outcome. None if the market
    is not two-outcome binary.
    """
    outcomes = _load_json_field(raw, "outcomes")
    if len(outcomes) != 2:
        return None
    for i, o in enumerate(outcomes):
        if str(o).strip().lower() == "yes":
            return i
    return 0


def parse_outcome(raw: dict) -> str | None:
    """YES/NO if the market resolved cleanly on its proposition leg, else None.

    Markets that split (e.g. 0.5/0.5) or lack a resolved UMA status return
    None and are excluded from the headline view.
    """
    if raw.get("umaResolutionStatus") not in (None, "resolved"):
        return None
    leg = proposition_leg(raw)
    if leg is None:
        return None
    prices = _load_json_field(raw, "outcomePrices")
    if len(prices) != 2:
        return None
    try:
        p = float(prices[leg])
    except (TypeError, ValueError):
        return None
    if p == 1.0:
        return "YES"
    if p == 0.0:
        return "NO"
    return None


def clob_token_for_leg(raw: dict) -> str | None:
    """CLOB token id of the proposition leg, used to fetch its price history."""
    leg = proposition_leg(raw)
    if leg is None:
        return None
    tokens = _load_json_field(raw, "clobTokenIds")
    if len(tokens) <= leg:
        return None
    return str(tokens[leg])


def derive_category(raw: dict) -> str | None:
    """Legacy markets carry a category field; newer ones only have tags."""
    if raw.get("category"):
        return str(raw["category"])
    tags = raw.get("tags") or []
    labels = [t.get("label") for t in tags if isinstance(t, dict) and t.get("label")]
    return labels[0] if labels else None


def trim_raw(raw: dict) -> dict:
    """Drop cosmetic fields and shrink nested events before storing raw_json."""
    out = {k: v for k, v in raw.items() if k not in _TRIM_KEYS}
    if isinstance(out.get("events"), list):
        out["events"] = [
            {k: e.get(k) for k in _EVENT_KEEP_KEYS if k in e}
            for e in out["events"]
            if isinstance(e, dict)
        ]
    if isinstance(out.get("tags"), list):
        out["tags"] = [
            t.get("label") for t in out["tags"]
            if isinstance(t, dict) and t.get("label")
        ]
    return out


def parse_market(raw: dict) -> MarketRow:
    """Normalize one Gamma market object into a MarketRow."""
    close_ts = normalize_iso(raw.get("closedTime")) or normalize_iso(raw.get("endDate"))
    return MarketRow(
        platform=PLATFORM,
        market_id=str(raw["id"]),
        title=str(raw.get("question") or ""),
        category=derive_category(raw),
        open_ts=normalize_iso(raw.get("startDate")) or normalize_iso(raw.get("createdAt")),
        close_ts=close_ts,
        # Polymarket exposes no separate resolution timestamp; closedTime is
        # when trading stopped, which on Polymarket coincides with resolution.
        resolve_ts=normalize_iso(raw.get("closedTime")),
        outcome=parse_outcome(raw),
        volume=raw.get("volumeNum"),
        liquidity=raw.get("liquidityNum"),
        raw_json=json.dumps(trim_raw(raw), separators=(",", ":")),
    )


def parse_price_history(history: dict, market_id: str) -> list[PriceRow]:
    """Convert a prices-history response into PriceRows.

    The response is {"history": [{"t": unix_seconds, "p": probability}]}.
    No bid/ask exists historically on Polymarket.
    """
    rows = []
    for point in history.get("history") or []:
        t, p = point.get("t"), point.get("p")
        if t is None or p is None:
            continue
        rows.append(PriceRow(
            platform=PLATFORM, market_id=market_id, ts=int(t),
            price=float(p), bid=None, ask=None, volume=None,
        ))
    return rows


class PolymarketClient:
    """Fetches Polymarket metadata pages and per-market price histories."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.gamma = BaseClient(PLATFORM, cfg.polymarket.gamma_base_url,
                                cfg.http, cfg.raw_dir())
        self.clob = BaseClient(PLATFORM, cfg.polymarket.clob_base_url,
                               cfg.http, cfg.raw_dir())

    def close(self) -> None:
        self.gamma.close()
        self.clob.close()

    def iter_closed_markets(self, since: dt.date, until: dt.date) -> Iterator[dict]:
        """Yield raw market dicts for every closed market in the frame.

        Frame: scheduled end date in [since, until), volume above the
        configured floor, started at least one day before the scheduled end.
        """
        day = since
        while day < until:
            yield from self._iter_day(day)
            day += dt.timedelta(days=1)

    def _iter_day(self, day: dt.date) -> Iterator[dict]:
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {
                "closed": "true",
                "end_date_min": day.isoformat(),
                "end_date_max": (day + dt.timedelta(days=1)).isoformat(),
                "start_date_max": (day - dt.timedelta(days=1)).isoformat(),
                "volume_num_min": self.cfg.polymarket.metadata_min_volume,
                "include_tag": "true",
                "limit": self.cfg.polymarket.page_size,
            }
            if cursor:
                params["after_cursor"] = cursor
            page = self.gamma.get_json("/markets/keyset", params)
            markets = page.get("markets") or []
            yield from markets
            cursor = page.get("next_cursor")
            if not cursor or not markets:
                return

    def fetch_price_history(self, clob_token_id: str) -> dict:
        """Full-life price history for one leg at configured fidelity."""
        return self.clob.get_json("/prices-history", {
            "market": clob_token_id,
            "interval": "max",
            "fidelity": self.cfg.ingestion.price_fidelity_minutes,
        })
