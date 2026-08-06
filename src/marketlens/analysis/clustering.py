"""Cluster-aware uncertainty for dependent contracts.

Every interval elsewhere in this project treats markets as independent
observations. They are not. A "who wins the nomination" event lists one
binary leg per candidate and exactly one of them resolves YES, so the
legs are mechanically negatively correlated. Sports events do the same
thing across a single game.

Treating those legs as independent understates uncertainty, because the
effective number of independent observations is closer to the number of
EVENTS than the number of markets. The functions here estimate that
inflation and widen intervals accordingly.

The method is a cluster bootstrap: resample whole events with
replacement rather than individual markets, recompute the statistic, and
read the spread of the resampled values. It makes no assumption about
the correlation structure inside an event, which matters because that
structure differs between a two-horse race and a 20-candidate field.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

SEED = 42


@dataclass(frozen=True)
class ClusteredInterval:
    point: float
    lo: float
    hi: float
    n_obs: int
    n_clusters: int

    @property
    def width(self) -> float:
        return self.hi - self.lo


def cluster_bootstrap(values: np.ndarray, clusters: np.ndarray,
                      statistic=np.mean, n_boot: int = 2000,
                      alpha: float = 0.05, seed: int = SEED
                      ) -> ClusteredInterval:
    """Percentile bootstrap interval resampling whole clusters.

    values and clusters are parallel arrays; clusters holds an event id
    per observation. Each bootstrap replicate draws clusters with
    replacement, concatenates their members, and recomputes the
    statistic, so correlated legs move together exactly as they do in the
    real data.
    """
    values = np.asarray(values, dtype=float)
    clusters = np.asarray(clusters)
    if values.size == 0:
        raise ValueError("empty input")

    uniq, inverse = np.unique(clusters, return_inverse=True)
    members = [np.flatnonzero(inverse == i) for i in range(uniq.size)]
    rng = np.random.default_rng(seed)

    stats = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        picked = rng.integers(0, uniq.size, uniq.size)
        idx = np.concatenate([members[p] for p in picked])
        stats[b] = statistic(values[idx])

    lo, hi = np.percentile(stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return ClusteredInterval(point=float(statistic(values)), lo=float(lo),
                             hi=float(hi), n_obs=int(values.size),
                             n_clusters=int(uniq.size))


def naive_interval(values: np.ndarray, alpha: float = 0.05
                   ) -> tuple[float, float]:
    """Textbook independent-observations interval, for comparison only."""
    values = np.asarray(values, dtype=float)
    n = values.size
    if n < 2:
        return (float("nan"), float("nan"))
    se = values.std(ddof=1) / np.sqrt(n)
    z = 1.959963984540054  # normal quantile at alpha = 0.05
    m = values.mean()
    return (float(m - z * se), float(m + z * se))


def design_effect(values: np.ndarray, clusters: np.ndarray,
                  n_boot: int = 2000, seed: int = SEED) -> float:
    """How much wider the honest interval is than the naive one.

    A design effect of 2 means clustering doubles the interval width, so
    the effective sample size is roughly a quarter of the raw count
    (width scales with the inverse square root of n).
    """
    clustered = cluster_bootstrap(values, clusters, n_boot=n_boot, seed=seed)
    lo, hi = naive_interval(values)
    naive_width = hi - lo
    if not np.isfinite(naive_width) or naive_width <= 0:
        return float("nan")
    return clustered.width / naive_width


def effective_sample_size(values: np.ndarray, clusters: np.ndarray,
                          n_boot: int = 2000, seed: int = SEED) -> float:
    """Independent-observation equivalent of a clustered sample."""
    deff = design_effect(values, clusters, n_boot=n_boot, seed=seed)
    if not np.isfinite(deff) or deff <= 0:
        return float("nan")
    return float(np.asarray(values).size / (deff ** 2))
