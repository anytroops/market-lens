"""Hand-computed tests for the paper-trading signal logic."""

import sqlite3

import pytest

from marketlens.live import paper
from marketlens.live.books import Book, Level


def book(bid, bid_size, ask, ask_size):
    return Book(bids=[Level(bid, bid_size)], asks=[Level(ask, ask_size)])


class TestPricePair:
    def test_obvious_arbitrage_is_found_at_the_touch(self):
        # PM yes available at 0.30, Kalshi no available at 0.45 (yes bid
        # 0.55). Gross 0.75 for a dollar, so a large edge even after fees.
        pm = book(0.29, 1000, 0.30, 1000)
        k = book(0.55, 1000, 0.56, 1000)
        q = paper.price_pair(pm, k, pm_fee=0.05, notional=None)
        assert q.direction == "pm_yes"
        assert q.edge > 0.2

    def test_aligned_books_offer_no_edge(self):
        pm = book(0.49, 1000, 0.51, 1000)
        k = book(0.49, 1000, 0.51, 1000)
        q = paper.price_pair(pm, k, pm_fee=0.05, notional=None)
        assert q.edge < 0  # crossing two spreads plus fees always loses

    def test_size_erodes_the_edge(self):
        # A one-cent-deep touch: only $30 available at the good price,
        # the rest is far worse.
        pm = Book(bids=[Level(0.29, 1000)],
                  asks=[Level(0.30, 100), Level(0.60, 10000)])
        k = book(0.55, 100000, 0.56, 100000)
        touch = paper.price_pair(pm, k, 0.05, None)
        big = paper.price_pair(pm, k, 0.05, 1000.0)
        assert big.edge < touch.edge

    def test_unfillable_size_returns_none(self):
        pm = book(0.29, 1, 0.30, 1)
        k = book(0.55, 1, 0.56, 1)
        q = paper.price_pair(pm, k, 0.05, 100000.0)
        assert q.cost is None and q.edge is None

    def test_direction_flips_when_kalshi_is_cheap(self):
        pm = book(0.70, 1000, 0.71, 1000)   # PM no costs 0.30
        k = book(0.29, 1000, 0.30, 1000)    # Kalshi yes costs 0.30
        q = paper.price_pair(pm, k, 0.05, None)
        assert q.direction == "k_yes"


class TestEvaluateAndRecord:
    def _conn(self):
        c = sqlite3.connect(":memory:")
        c.executescript("""
            CREATE TABLE markets (platform TEXT, market_id TEXT, outcome TEXT);
        """)
        paper.ensure_schema(c)
        return c

    def test_evaluate_reports_touch_and_every_size(self):
        sig = paper.evaluate(book(0.29, 1000, 0.30, 1000),
                             book(0.55, 1000, 0.56, 1000), "Politics")
        for key in ("touch_cost", "touch_edge", "exec_cost_50",
                    "exec_edge_200", "exec_cost_1000", "direction"):
            assert key in sig
        assert sig["pm_best_ask"] == pytest.approx(0.30)

    def test_record_then_settle_consistent_pair_pays_one(self):
        # A correctly matched pair resolves the SAME way on both venues.
        # Long PM yes plus Kalshi no then collects exactly one dollar,
        # whichever way the event went.
        c = self._conn()
        sig = paper.evaluate(book(0.29, 1000, 0.30, 1000),
                             book(0.55, 1000, 0.56, 1000), "Politics")
        paper.record(c, "pm1", "k1", sig, ts=1000)
        c.execute("INSERT INTO markets VALUES ('polymarket','pm1','YES')")
        c.execute("INSERT INTO markets VALUES ('kalshi','k1','YES')")
        assert paper.settle(c) == 1
        payout, settled = c.execute(
            "SELECT realized_payout, settled FROM paper_signals").fetchone()
        assert payout == 1.0 and settled == 1

    def test_settle_flags_an_inconsistent_pair(self):
        c = self._conn()
        sig = paper.evaluate(book(0.29, 1000, 0.30, 1000),
                             book(0.55, 1000, 0.56, 1000), "Politics")
        paper.record(c, "pm1", "k1", sig, ts=1000)
        # Legs resolve opposite ways: the pair was not really the same
        # proposition, so the hedge pays 2 instead of 1 and the mismatch
        # is visible rather than silent.
        c.execute("INSERT INTO markets VALUES ('polymarket','pm1','YES')")
        c.execute("INSERT INTO markets VALUES ('kalshi','k1','NO')")
        paper.settle(c)
        assert c.execute(
            "SELECT realized_payout FROM paper_signals").fetchone()[0] == 2.0

    def test_settle_flags_the_other_mismatch_direction(self):
        c = self._conn()
        sig = paper.evaluate(book(0.29, 1000, 0.30, 1000),
                             book(0.55, 1000, 0.56, 1000), "Politics")
        paper.record(c, "pm1", "k1", sig, ts=1000)
        c.execute("INSERT INTO markets VALUES ('polymarket','pm1','NO')")
        c.execute("INSERT INTO markets VALUES ('kalshi','k1','YES')")
        paper.settle(c)
        assert c.execute(
            "SELECT realized_payout FROM paper_signals").fetchone()[0] == 0.0

    def test_unresolved_markets_are_left_alone(self):
        c = self._conn()
        sig = paper.evaluate(book(0.29, 1000, 0.30, 1000),
                             book(0.55, 1000, 0.56, 1000), "Politics")
        paper.record(c, "pm1", "k1", sig, ts=1000)
        c.execute("INSERT INTO markets VALUES ('polymarket','pm1',NULL)")
        c.execute("INSERT INTO markets VALUES ('kalshi','k1',NULL)")
        assert paper.settle(c) == 0

    def test_duplicate_signal_at_same_timestamp_is_ignored(self):
        c = self._conn()
        sig = paper.evaluate(book(0.29, 1000, 0.30, 1000),
                             book(0.55, 1000, 0.56, 1000), "Politics")
        paper.record(c, "pm1", "k1", sig, ts=1000)
        paper.record(c, "pm1", "k1", sig, ts=1000)
        assert c.execute("SELECT COUNT(*) FROM paper_signals").fetchone()[0] == 1
