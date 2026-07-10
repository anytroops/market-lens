"""Unit tests for the pure Kalshi parsing helpers."""

from marketlens.ingest import kalshi as km


class TestDollars:
    def test_parses_dollar_strings(self):
        assert km._dollars("0.5800") == 0.58

    def test_empty_and_none(self):
        assert km._dollars("") is None
        assert km._dollars(None) is None
        assert km._dollars("abc") is None


class TestParseMarket:
    def test_fixture(self, fixture):
        raw = fixture("kalshi_market")
        row = km.parse_market(raw, category="Exotics")
        assert row is not None
        assert row.platform == "kalshi"
        assert row.market_id == raw["ticker"]
        assert row.outcome == {"yes": "YES", "no": "NO"}[raw["result"]]
        assert row.category == "Exotics"
        assert row.open_ts.endswith("Z") and row.close_ts.endswith("Z")

    def test_non_binary_returns_none(self, fixture):
        raw = dict(fixture("kalshi_market"), market_type="scalar")
        assert km.parse_market(raw, None) is None

    def test_unsettled_result_gives_no_outcome(self, fixture):
        raw = dict(fixture("kalshi_market"), result="")
        row = km.parse_market(raw, None)
        assert row is not None and row.outcome is None


class TestParseCandlesticks:
    def test_fixture_mixed_candles(self, fixture):
        payload = fixture("kalshi_candles")
        rows = km.parse_candlesticks(payload, "T1")
        assert len(rows) == len(payload["candlesticks"])
        # First fixture candle has no trades: price None, bid/ask present.
        no_trade = rows[0]
        assert no_trade.price is None
        assert no_trade.bid is not None and no_trade.ask is not None
        # Traded candles carry a close price in [0, 1].
        traded = rows[1]
        assert traded.price is not None and 0 <= traded.price <= 1

    def test_empty_payload(self):
        assert km.parse_candlesticks({}, "T1") == []


class TestKeepSeries:
    def _cfg(self):
        from marketlens.config import Config
        return Config(
            ingestion={"since": "2024-07-09", "until": "2026-07-09"},
            storage={},
            http={"user_agent": "test"},
            polymarket={"gamma_base_url": "x", "clob_base_url": "x"},
            kalshi={
                "base_url": "x",
                "skip_frequencies": ["fifteen_min", "hourly"],
                "skip_ticker_prefixes": ["KXMVE"],
                "skip_categories": ["Exotics"],
            },
        )

    def test_skips_high_frequency(self):
        cfg = self._cfg()
        assert not km.keep_series({"ticker": "KXBTC15M", "frequency": "fifteen_min"}, cfg)
        assert not km.keep_series({"ticker": "KXBTCH", "frequency": "hourly"}, cfg)

    def test_skips_mve_and_exotics(self):
        cfg = self._cfg()
        assert not km.keep_series(
            {"ticker": "KXMVECROSSCATEGORY", "frequency": "custom"}, cfg)
        assert not km.keep_series(
            {"ticker": "KXOTHER", "frequency": "custom", "category": "Exotics"}, cfg)

    def test_keeps_normal_series(self):
        cfg = self._cfg()
        assert km.keep_series(
            {"ticker": "KXFED", "frequency": "monthly", "category": "Economics"}, cfg)


class TestSeriesTicker:
    def test_prefix_of_event_ticker(self):
        assert km.series_ticker_of({"event_ticker": "KXFED-26JUN"}) == "KXFED"

    def test_falls_back_to_ticker(self):
        assert km.series_ticker_of({"ticker": "KXFED-26JUN-T5.25"}) == "KXFED"
