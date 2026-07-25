"""Hand-computed toy cases for the prediction comparison core."""

import numpy as np
import pandas as pd
import pytest

from marketlens.analysis import prediction as pr


class TestLogit:
    def test_symmetry_and_known_values(self):
        assert pr.logit(np.array([0.5]))[0] == pytest.approx(0.0)
        assert pr.logit(np.array([0.75]))[0] == pytest.approx(np.log(3))
        assert pr.logit(np.array([0.25]))[0] == pytest.approx(-np.log(3))

    def test_extremes_stay_finite(self):
        assert np.isfinite(pr.logit(np.array([0.0, 1.0]))).all()


class TestLogLoss:
    def test_always_half_is_ln2(self):
        assert pr.log_loss([1, 0], [0.5, 0.5]) == pytest.approx(np.log(2))

    def test_perfect_forecast_near_zero(self):
        assert pr.log_loss([1, 0], [1.0, 0.0]) == pytest.approx(0.0, abs=1e-5)

    def test_hand_computed(self):
        # -(ln 0.8 + ln 0.7) / 2
        expected = -(np.log(0.8) + np.log(0.7)) / 2
        assert pr.log_loss([1, 0], [0.8, 0.3]) == pytest.approx(expected)

    def test_confident_and_wrong_is_heavily_penalized(self):
        assert pr.log_loss([1], [0.01]) > pr.log_loss([1], [0.4])

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            pr.log_loss([], [])


class TestPairedLossDifference:
    def test_identical_models_have_zero_difference(self):
        y = [1, 0, 1, 0]
        p = [0.7, 0.3, 0.6, 0.4]
        r = pr.paired_loss_difference(y, p, p)
        assert r["mean_difference"] == pytest.approx(0.0)
        assert r["n"] == 4

    def test_sign_positive_when_first_model_is_worse(self):
        y = [1, 1, 1, 1]
        worse, better = [0.5] * 4, [0.9] * 4
        r = pr.paired_loss_difference(y, worse, better)
        assert r["mean_difference"] > 0

    def test_consistent_small_edge_gives_large_t(self):
        # An informative forecaster with VARYING confidence beats a
        # constant 0.5 by a margin that survives the paired test.
        rng = np.random.default_rng(0)
        y = rng.integers(0, 2, 400)
        noise = rng.uniform(0.0, 0.15, 400)
        good = np.where(y == 1, 0.60 + noise, 0.40 - noise)
        meh = np.full(400, 0.5)
        r = pr.paired_loss_difference(y, meh, good)
        assert r["t_stat"] > 5  # consistent edge, not noise

    def test_degenerate_zero_variance_is_not_significant(self):
        # Both models constant: the difference has no variance, so no
        # t statistic exists rather than an infinite one.
        y = [1, 1, 1, 1]
        r = pr.paired_loss_difference(y, [0.5] * 4, [0.6] * 4)
        assert np.isnan(r["t_stat"])

    def test_too_few_observations(self):
        with pytest.raises(ValueError):
            pr.paired_loss_difference([1], [0.5], [0.6])


class TestTemporalSplit:
    def test_split_is_chronological_and_disjoint(self):
        df = pd.DataFrame({"d": pd.to_datetime(
            ["2026-01-01", "2026-02-01", "2026-03-01", "2026-04-01"])})
        train, test = pr.temporal_split(df, "d", test_fraction=0.5)
        assert len(train) + len(test) == 4
        assert train["d"].max() < test["d"].min()

    def test_no_date_spans_both_sides(self):
        df = pd.DataFrame({"d": pd.to_datetime(
            ["2026-01-01"] * 3 + ["2026-02-01"] * 3)})
        train, test = pr.temporal_split(df, "d", test_fraction=0.5)
        assert set(train["d"]).isdisjoint(set(test["d"]))

    def test_empty(self):
        df = pd.DataFrame({"d": pd.to_datetime([])})
        train, test = pr.temporal_split(df, "d")
        assert train.empty and test.empty


class TestMomentum:
    def test_doubling_a_longshot_beats_a_one_point_move(self):
        assert pr.momentum(0.02, 0.01) > pr.momentum(0.51, 0.50)

    def test_no_history_is_zero(self):
        assert pr.momentum(0.5, None) == 0.0

    def test_sign(self):
        assert pr.momentum(0.6, 0.4) > 0
        assert pr.momentum(0.4, 0.6) < 0
