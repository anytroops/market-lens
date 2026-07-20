"""Hand-computed toy cases for the arbitrage backtest core."""

import datetime as dt

import pandas as pd
import pytest

from marketlens.analysis import backtest as bt


class TestTakerFee:
    def test_formula(self):
        assert bt.taker_fee(0.07, 0.5) == pytest.approx(0.0175)
        assert bt.taker_fee(0.05, 0.0) == 0.0


class TestBestEntry:
    def test_hand_computed_direction_a(self):
        # PM YES at 0.40 (+1pt slip = 0.41), Kalshi NO at 1 - 0.55 = 0.45.
        # Fees: 0.04*0.41*0.59 = 0.009676; 0.07*0.45*0.55 = 0.0173250
        # cost_a = 0.41 + 0.45 + 0.009676 + 0.017325 = 0.887001
        book = bt.LegBook(pm_price=0.40, k_yes_ask=0.60, k_yes_bid=0.55)
        e = bt.best_entry(book, pm_fee_rate=0.04, kalshi_fee_rate=0.07,
                          slippage_points=1.0)
        assert e.direction == "pm_yes"
        assert e.cost == pytest.approx(0.887001)
        assert e.edge == pytest.approx(1 - 0.887001)

    def test_direction_b_when_kalshi_cheap(self):
        # Kalshi YES ask 0.30, PM NO at 1-0.45+0.01 = 0.56.
        book = bt.LegBook(pm_price=0.45, k_yes_ask=0.30, k_yes_bid=0.25)
        e = bt.best_entry(book, 0.04, 0.07, 1.0)
        assert e.direction == "k_yes"

    def test_no_free_lunch_when_aligned(self):
        # Identical fair prices: cost must exceed 1 (fees + slippage).
        book = bt.LegBook(pm_price=0.50, k_yes_ask=0.51, k_yes_bid=0.49)
        e = bt.best_entry(book, 0.04, 0.07, 1.0)
        assert e.edge < 0


class TestRealizedPayout:
    def test_correct_pair_pays_exactly_one(self):
        assert bt.realized_payout("pm_yes", "YES", "YES") == 1.0
        assert bt.realized_payout("pm_yes", "NO", "NO") == 1.0
        assert bt.realized_payout("k_yes", "NO", "NO") == 1.0

    def test_mismatched_pair_pays_zero_or_two(self):
        assert bt.realized_payout("pm_yes", "NO", "YES") == 0.0
        assert bt.realized_payout("pm_yes", "YES", "NO") == 2.0


class TestBacktestPair:
    def _days(self):
        idx = [dt.date(2026, 6, 1), dt.date(2026, 6, 2)]
        return pd.DataFrame(
            {"pm": [0.50, 0.30], "k_ask": [0.51, 0.55], "k_bid": [0.49, 0.53]},
            index=idx)

    def test_enters_first_qualifying_day_only(self):
        # Day 1: aligned, no edge. Day 2: PM 0.30 vs Kalshi bid 0.53:
        # buy PM YES 0.31, K NO 0.47, fees small: cost < 1.
        t = bt.backtest_pair(self._days(), "YES", "YES", 0.04, 0.07, 1.0,
                             edge_threshold=0.02,
                             resolve_day=dt.date(2026, 6, 8))
        assert t is not None
        assert t.entry_day == dt.date(2026, 6, 2)
        assert t.direction == "pm_yes"
        assert t.days_held == 6
        assert t.realized_payout == 1.0
        assert t.realized_pnl == pytest.approx(t.edge)
        assert t.annualized == pytest.approx((t.edge / t.cost) * 365 / 6)

    def test_no_entry_when_edge_below_threshold(self):
        t = bt.backtest_pair(self._days(), "YES", "YES", 0.04, 0.07, 1.0,
                             edge_threshold=0.20,
                             resolve_day=dt.date(2026, 6, 8))
        assert t is None
