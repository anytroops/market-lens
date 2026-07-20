"""Hand-computed toy cases for the calibration statistics core."""

import numpy as np
import pytest

from marketlens.analysis import calibration as cal


class TestWilsonInterval:
    def test_known_value_8_of_10(self):
        # Textbook Wilson interval for 8 successes in 10 trials, z=1.96.
        lo, hi = cal.wilson_interval(8, 10)
        assert lo == pytest.approx(0.4902, abs=1e-3)
        assert hi == pytest.approx(0.9433, abs=1e-3)

    def test_stays_inside_unit_interval(self):
        lo, hi = cal.wilson_interval(0, 5)
        assert lo == 0.0 and 0 < hi < 1
        lo, hi = cal.wilson_interval(5, 5)
        assert 0 < lo < 1 and hi == 1.0

    def test_empty(self):
        assert cal.wilson_interval(0, 0) == (0.0, 1.0)


class TestBrierScore:
    def test_hand_computed(self):
        # ((1-1)^2 + (0.5-0)^2 + (0-0)^2) / 3 = 0.25/3
        assert cal.brier_score([1, 0.5, 0], [1, 0, 0]) == pytest.approx(0.25 / 3)

    def test_perfect_and_worst(self):
        assert cal.brier_score([1, 0], [1, 0]) == 0.0
        assert cal.brier_score([1, 0], [0, 1]) == 1.0

    def test_coin_flip_reference(self):
        assert cal.brier_score([0.5, 0.5], [1, 0]) == 0.25

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            cal.brier_score([], [])


class TestMurphyDecomposition:
    # Toy set: two forecasts of 0.05 (one resolves YES: badly calibrated)
    # and two of 0.95 (both YES). All values hand-computed in the comments.
    PROBS = np.array([0.05, 0.05, 0.95, 0.95])
    OUTCOMES = np.array([0, 1, 1, 1])

    def test_hand_computed_components(self):
        d = cal.murphy_decomposition(self.PROBS, self.OUTCOMES)
        # base rate 3/4; uncertainty = 0.75 * 0.25
        assert d.base_rate == 0.75
        assert d.uncertainty == pytest.approx(0.1875)
        # bin [0,0.1): rel 0.5*(0.05-0.5)^2, bin [0.9,1): rel 0.5*(0.95-1)^2
        assert d.reliability == pytest.approx(0.5 * 0.2025 + 0.5 * 0.0025)
        # res 0.5*(0.5-0.75)^2 + 0.5*(1-0.75)^2
        assert d.resolution == pytest.approx(0.0625)
        assert d.brier == pytest.approx(0.2275)

    def test_identity_holds_when_forecasts_equal_bin_means(self):
        d = cal.murphy_decomposition(self.PROBS, self.OUTCOMES)
        assert d.brier == pytest.approx(d.reliability - d.resolution + d.uncertainty)


class TestCalibrationTable:
    def test_bins_and_wilson(self):
        table = cal.calibration_table(
            np.array([0.05, 0.05, 0.95, 0.95]), np.array([0, 1, 1, 1]))
        assert len(table) == 2
        low, high = table
        assert (low.n, low.yes_rate) == (2, 0.5)
        assert (high.n, high.yes_rate) == (2, 1.0)
        assert low.ci_lo < 0.5 < low.ci_hi
        assert low.mean_prob == pytest.approx(0.05)

    def test_prob_of_exactly_one_lands_in_top_bin(self):
        table = cal.calibration_table(np.array([1.0]), np.array([1]))
        assert table[0].lo == pytest.approx(0.9)


class TestStripPlaceholderPrefix:
    def test_leading_run_dropped(self):
        ts = np.array([1, 2, 3, 4])
        px = np.array([0.5, 0.5, 0.6, 0.5])
        t2, p2 = cal.strip_placeholder_prefix(ts, px)
        assert list(t2) == [3, 4]
        assert list(p2) == [0.6, 0.5]  # interior 0.5 survives

    def test_all_placeholder_series_becomes_empty(self):
        t2, p2 = cal.strip_placeholder_prefix(
            np.array([1, 2]), np.array([0.5, 0.5]))
        assert len(t2) == 0 and len(p2) == 0

    def test_unsorted_input(self):
        t2, p2 = cal.strip_placeholder_prefix(
            np.array([3, 1, 2]), np.array([0.7, 0.5, 0.5]))
        assert list(t2) == [3] and list(p2) == [0.7]

    def test_no_placeholder(self):
        t2, p2 = cal.strip_placeholder_prefix(
            np.array([1, 2]), np.array([0.3, 0.4]))
        assert len(t2) == 2


class TestPriceAtHorizon:
    TS = np.array([100, 200, 300])
    PX = np.array([0.1, 0.2, 0.3])

    def test_takes_last_price_at_or_before_cutoff(self):
        assert cal.price_at_horizon(self.TS, self.PX, 300, 100) == 0.2

    def test_exact_boundary_included(self):
        assert cal.price_at_horizon(self.TS, self.PX, 400, 100) == 0.3

    def test_no_history_early_enough(self):
        assert cal.price_at_horizon(self.TS, self.PX, 300, 250) is None

    def test_unsorted_input(self):
        assert cal.price_at_horizon(
            np.array([300, 100, 200]), np.array([0.3, 0.1, 0.2]), 300, 100) == 0.2
