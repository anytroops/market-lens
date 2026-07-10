"""Tests for idempotent loaders, the headline view, sampling, and stats helpers."""

import sqlite3

import pytest

from marketlens.db import loaders, schema
from marketlens.ingest.runner import deterministic_sample
from marketlens.quality import coverage_ratio, percent


@pytest.fixture
def conn():
    c = schema.connect(":memory:", min_lifetime_hours=24)
    yield c
    c.close()


def _market(market_id: str, open_ts: str, close_ts: str, outcome: str = "YES",
            platform: str = "polymarket", volume: float = 100.0):
    return loaders.MarketRow(
        platform=platform, market_id=market_id, title=f"m {market_id}",
        category="test", open_ts=open_ts, close_ts=close_ts,
        resolve_ts=close_ts, outcome=outcome, volume=volume,
        liquidity=None, raw_json="{}",
    )


class TestIdempotency:
    def test_market_upsert_never_duplicates(self, conn):
        row = _market("a", "2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z")
        loaders.upsert_markets(conn, [row])
        loaders.upsert_markets(conn, [row])
        assert conn.execute("SELECT COUNT(*) FROM markets").fetchone()[0] == 1

    def test_market_upsert_updates_fields(self, conn):
        loaders.upsert_markets(conn, [
            _market("a", "2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z", volume=1)])
        loaders.upsert_markets(conn, [
            _market("a", "2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z", volume=2)])
        assert conn.execute("SELECT volume FROM markets").fetchone()[0] == 2

    def test_price_upsert_never_duplicates(self, conn):
        row = loaders.PriceRow("kalshi", "t", 1700000000, 0.5, 0.49, 0.51, 10)
        loaders.upsert_prices(conn, [row])
        loaders.upsert_prices(conn, [row])
        assert conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 1


class TestHeadlineView:
    def test_short_market_excluded(self, conn):
        loaders.upsert_markets(conn, [
            _market("short", "2025-01-01T00:00:00Z", "2025-01-01T12:00:00Z"),
            _market("long", "2025-01-01T00:00:00Z", "2025-01-03T00:00:00Z"),
        ])
        ids = [r[0] for r in conn.execute("SELECT market_id FROM headline_markets")]
        assert ids == ["long"]

    def test_exactly_24h_included(self, conn):
        loaders.upsert_markets(conn, [
            _market("edge", "2025-01-01T00:00:00Z", "2025-01-02T00:00:00Z")])
        assert conn.execute("SELECT COUNT(*) FROM headline_markets").fetchone()[0] == 1

    def test_unresolved_excluded(self, conn):
        loaders.upsert_markets(conn, [
            _market("u", "2025-01-01T00:00:00Z", "2025-02-01T00:00:00Z", outcome=None)])
        assert conn.execute("SELECT COUNT(*) FROM headline_markets").fetchone()[0] == 0

    def test_threshold_is_configurable(self):
        c = schema.connect(":memory:", min_lifetime_hours=1)
        loaders.upsert_markets(c, [
            _market("short", "2025-01-01T00:00:00Z", "2025-01-01T02:00:00Z")])
        assert c.execute("SELECT COUNT(*) FROM headline_markets").fetchone()[0] == 1
        c.close()


class TestDeterministicSample:
    def test_reproducible(self):
        ids = [f"m{i}" for i in range(1000)]
        assert deterministic_sample(ids, 50, 42) == deterministic_sample(ids, 50, 42)

    def test_order_independent(self):
        ids = [f"m{i}" for i in range(1000)]
        assert deterministic_sample(ids, 50, 42) == \
            deterministic_sample(list(reversed(ids)), 50, 42)

    def test_k_larger_than_population_returns_all(self):
        assert deterministic_sample(["b", "a"], 10, 42) == ["a", "b"]

    def test_is_subset(self):
        ids = [f"m{i}" for i in range(100)]
        assert set(deterministic_sample(ids, 10, 7)) <= set(ids)


class TestStatsHelpers:
    def test_percent(self):
        assert percent(1, 4) == 25.0
        assert percent(0, 0) == 0.0

    def test_coverage_ratio(self):
        assert coverage_ratio(80, 100) == 0.8
        assert coverage_ratio(120, 100) == 1.0  # capped
        assert coverage_ratio(0, 0) == 0.0
        assert coverage_ratio(1, 0) == 1.0
