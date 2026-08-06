"""Tests for cluster-aware uncertainty."""

import numpy as np
import pytest

from marketlens.analysis import clustering as cl


class TestClusterBootstrap:
    def test_independent_data_matches_the_naive_interval(self):
        # Every observation its own cluster: clustering should change
        # essentially nothing.
        rng = np.random.default_rng(0)
        v = rng.normal(size=400)
        ci = cl.cluster_bootstrap(v, np.arange(400), n_boot=500)
        lo, hi = cl.naive_interval(v)
        assert ci.width == pytest.approx(hi - lo, rel=0.25)
        assert ci.n_clusters == 400

    def test_perfectly_correlated_clusters_widen_the_interval(self):
        # 40 events of 10 identical legs each: the real sample size is 40,
        # not 400, so the honest interval must be much wider.
        rng = np.random.default_rng(1)
        per_event = rng.normal(size=40)
        v = np.repeat(per_event, 10)
        clusters = np.repeat(np.arange(40), 10)
        ci = cl.cluster_bootstrap(v, clusters, n_boot=500)
        lo, hi = cl.naive_interval(v)
        assert ci.width > (hi - lo) * 2
        assert ci.n_obs == 400 and ci.n_clusters == 40

    def test_point_estimate_is_the_plain_statistic(self):
        v = np.array([1.0, 2.0, 3.0, 4.0])
        ci = cl.cluster_bootstrap(v, np.array([0, 0, 1, 1]), n_boot=200)
        assert ci.point == pytest.approx(2.5)

    def test_reproducible_for_a_seed(self):
        v = np.random.default_rng(2).normal(size=100)
        c = np.repeat(np.arange(20), 5)
        a = cl.cluster_bootstrap(v, c, n_boot=200, seed=7)
        b = cl.cluster_bootstrap(v, c, n_boot=200, seed=7)
        assert (a.lo, a.hi) == (b.lo, b.hi)

    def test_works_for_a_proportion(self):
        outcomes = np.array([1.0] * 30 + [0.0] * 70)
        clusters = np.repeat(np.arange(20), 5)
        ci = cl.cluster_bootstrap(outcomes, clusters, n_boot=300)
        assert 0.0 <= ci.lo <= ci.point <= ci.hi <= 1.0
        assert ci.point == pytest.approx(0.30)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            cl.cluster_bootstrap(np.array([]), np.array([]))


class TestDesignEffect:
    def test_near_one_when_observations_are_independent(self):
        rng = np.random.default_rng(3)
        v = rng.normal(size=400)
        d = cl.design_effect(v, np.arange(400), n_boot=400)
        assert 0.75 < d < 1.35

    def test_large_when_clusters_are_redundant(self):
        v = np.repeat(np.random.default_rng(4).normal(size=40), 10)
        d = cl.design_effect(v, np.repeat(np.arange(40), 10), n_boot=400)
        assert d > 2

    def test_effective_sample_size_shrinks_with_redundancy(self):
        v = np.repeat(np.random.default_rng(5).normal(size=40), 10)
        c = np.repeat(np.arange(40), 10)
        ess = cl.effective_sample_size(v, c, n_boot=400)
        assert ess < 120  # far below the raw 400
