"""Hand-computed toy cases for the divergence analysis core."""

import numpy as np
import pandas as pd
import pytest

from marketlens.analysis import divergence as dv

DAY = 86400


def _series(day_prices: dict[int, float]) -> pd.Series:
    ts = np.array([d * DAY for d in day_prices])
    px = np.array(list(day_prices.values()))
    return dv.daily_series(ts, px)


class TestDailySeries:
    def test_last_observation_of_day_wins(self):
        ts = np.array([10, 20, DAY + 5])
        px = np.array([0.4, 0.5, 0.6])
        s = dv.daily_series(ts, px)
        assert list(s.values) == [0.5, 0.6]

    def test_empty(self):
        assert dv.daily_series(np.array([]), np.array([])).empty


class TestAlignPair:
    def test_common_days_and_spread_points(self):
        pm = _series({0: 0.60, 1: 0.70, 2: 0.80})
        k = _series({1: 0.65, 2: 0.80, 3: 0.90})
        df = dv.align_pair(pm, k)
        assert len(df) == 2  # days 1 and 2 only
        assert df["spread"].tolist() == pytest.approx([5.0, 0.0])

    def test_inverse_orientation_flips_kalshi(self):
        pm = _series({0: 0.60})
        k = _series({0: 0.35})  # kalshi asks the other side
        df = dv.align_pair(pm, k, orientation="inverse")
        # 1 - 0.35 = 0.65, spread = -5 points
        assert df["spread"].tolist() == pytest.approx([-5.0])


class TestSpreadStats:
    def test_hand_computed(self):
        s = pd.Series([1.0, -3.0, 6.0, -12.0])
        st = dv.spread_stats(s)
        assert st.n_days == 4
        assert st.mean_abs == pytest.approx(5.5)
        assert st.max_abs == 12.0
        assert st.pct_gt2 == 75.0
        assert st.pct_gt5 == 50.0
        assert st.pct_gt10 == 25.0

    def test_empty(self):
        assert dv.spread_stats(pd.Series(dtype=float)) is None


class TestHalfLife:
    def test_simple_event(self):
        # Day 2: gap opens at 8 points; day 5: first drop to <= 4.
        s = pd.Series([0, 1, 8, 6, 5, 3, 1])
        assert dv.half_life_events(s, threshold=5) == [3.0]

    def test_widening_resets_the_clock(self):
        # Opens at 6 (day 1), widens to 10 (day 2), halves at day 4 (<=5).
        s = pd.Series([0, 6, 10, 7, 5])
        assert dv.half_life_events(s, threshold=5) == [2.0]

    def test_censored_event_excluded(self):
        s = pd.Series([0, 8, 7, 6])  # never halves before the series ends
        assert dv.half_life_events(s, threshold=5) == []

    def test_two_events(self):
        s = pd.Series([8, 3, 0, 6, 2])
        assert dv.half_life_events(s, threshold=5) == [1.0, 1.0]

    def test_sign_agnostic(self):
        s = pd.Series([-8, -3])
        assert dv.half_life_events(s, threshold=5) == [1.0]


class TestLeadLag:
    def test_perfect_one_day_lead(self):
        # Kalshi copies Polymarket's move one day later.
        pm = pd.Series([0.1, 0.3, 0.2, 0.5, 0.4, 0.6])
        k = pd.Series([0.2, 0.1, 0.3, 0.2, 0.5, 0.4])
        df = pd.DataFrame({"pm": pm, "kalshi": k})
        cc = dv.lead_lag_correlation(df, max_lag=1)
        assert cc[1] == pytest.approx(1.0)  # pm leads by one day
        assert cc[1] > cc[0]
