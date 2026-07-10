"""Unit tests for the pure Polymarket parsing helpers."""

import json

from marketlens.ingest import polymarket as pm


class TestNormalizeIso:
    def test_standard_z(self):
        assert pm.normalize_iso("2026-06-30T00:00:00Z") == "2026-06-30T00:00:00Z"

    def test_microseconds(self):
        assert pm.normalize_iso("2025-06-19T18:02:51.278733Z") == "2025-06-19T18:02:51Z"

    def test_nonstandard_closed_time(self):
        # Gamma's closedTime uses a space separator and bare '+00' offset.
        assert pm.normalize_iso("2026-06-15 06:04:30+00") == "2026-06-15T06:04:30Z"

    def test_date_only(self):
        assert pm.normalize_iso("2026-06-30") == "2026-06-30T00:00:00Z"

    def test_none_and_garbage(self):
        assert pm.normalize_iso(None) is None
        assert pm.normalize_iso("") is None
        assert pm.normalize_iso("not a date") is None


class TestOutcome:
    def _market(self, outcomes, prices, status="resolved"):
        return {
            "outcomes": json.dumps(outcomes),
            "outcomePrices": json.dumps(prices),
            "umaResolutionStatus": status,
        }

    def test_yes_wins(self):
        assert pm.parse_outcome(self._market(["Yes", "No"], ["1", "0"])) == "YES"

    def test_no_wins(self):
        assert pm.parse_outcome(self._market(["Yes", "No"], ["0", "1"])) == "NO"

    def test_yes_leg_found_when_second(self):
        # If outcomes are ordered No/Yes, the proposition leg is still Yes.
        assert pm.parse_outcome(self._market(["No", "Yes"], ["0", "1"])) == "YES"

    def test_team_markets_use_first_outcome(self):
        m = self._market(["Chiefs", "Bills"], ["0", "1"])
        assert pm.parse_outcome(m) == "NO"
        assert pm.proposition_leg(m) == 0

    def test_split_resolution_is_not_clean(self):
        assert pm.parse_outcome(self._market(["Yes", "No"], ["0.5", "0.5"])) is None

    def test_unresolved_status(self):
        m = self._market(["Yes", "No"], ["1", "0"], status="disputed")
        assert pm.parse_outcome(m) is None

    def test_multi_outcome_is_not_binary(self):
        m = self._market(["A", "B", "C"], ["1", "0", "0"])
        assert pm.parse_outcome(m) is None


class TestParseMarket:
    def test_fixture_roundtrip(self, fixture):
        raw = fixture("polymarket_market")
        row = pm.parse_market(raw)
        assert row.platform == "polymarket"
        assert row.market_id == str(raw["id"])
        assert row.title == raw["question"]
        assert row.outcome == "YES"  # fixture resolved 1/0 on the Yes leg
        assert row.open_ts.endswith("Z") and row.close_ts.endswith("Z")
        assert row.volume == raw["volumeNum"]
        stored = json.loads(row.raw_json)
        assert "image" not in stored
        assert "clobTokenIds" in stored

    def test_clob_token_matches_proposition_leg(self, fixture):
        raw = fixture("polymarket_market")
        token = pm.clob_token_for_leg(raw)
        assert token == json.loads(raw["clobTokenIds"])[0]

    def test_trim_raw_shrinks_events(self, fixture):
        raw = fixture("polymarket_market")
        trimmed = pm.trim_raw(raw)
        for e in trimmed.get("events", []):
            assert set(e) <= pm._EVENT_KEEP_KEYS


class TestParsePriceHistory:
    def test_fixture(self, fixture):
        raw = fixture("polymarket_prices")
        rows = pm.parse_price_history(raw, "m1")
        assert len(rows) == len(raw["history"])
        first = rows[0]
        assert first.ts == raw["history"][0]["t"]
        assert first.price == raw["history"][0]["p"]
        assert first.bid is None and first.ask is None

    def test_empty(self):
        assert pm.parse_price_history({"history": []}, "m1") == []
        assert pm.parse_price_history({}, "m1") == []
