"""Calibration statistics (Phase 3).

Small pure functions, each with a hand-computable unit test. Probabilities
are floats in [0, 1]; outcomes are 0/1 ints where 1 means the market's
proposition resolved YES.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Preferred over the normal approximation because it stays inside [0, 1]
    and behaves sensibly for small n or extreme proportions.
    """
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def brier_score(probs: np.ndarray, outcomes: np.ndarray) -> float:
    """Mean squared error between probability forecasts and 0/1 outcomes.

    0 is perfect; 0.25 is the score of always forecasting 0.5.
    """
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    if probs.size == 0:
        raise ValueError("empty input")
    return float(np.mean((probs - outcomes) ** 2))


@dataclass(frozen=True)
class MurphyDecomposition:
    """Brier = reliability - resolution + uncertainty (within-bin variant).

    reliability: weighted mean squared gap between a bin's mean forecast and
    its empirical frequency. Calibration error, lower is better.
    resolution: weighted mean squared gap between bin frequencies and the
    base rate. Discrimination, higher is better.
    uncertainty: base_rate * (1 - base_rate), a property of the event set.
    """
    brier: float
    reliability: float
    resolution: float
    uncertainty: float
    base_rate: float


def murphy_decomposition(probs: np.ndarray, outcomes: np.ndarray,
                         n_bins: int = 10) -> MurphyDecomposition:
    """Decompose the Brier score over equal-width probability bins.

    The identity Brier = REL - RES + UNC holds exactly when every forecast
    in a bin is replaced by the bin mean; with raw forecasts a small
    within-bin variance term remains, which is standard and noted in the
    results write-up.
    """
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    if probs.size == 0:
        raise ValueError("empty input")
    n = probs.size
    base = float(outcomes.mean())
    bins = np.clip((probs * n_bins).astype(int), 0, n_bins - 1)
    rel = 0.0
    res = 0.0
    for b in range(n_bins):
        mask = bins == b
        nb = int(mask.sum())
        if nb == 0:
            continue
        mean_p = float(probs[mask].mean())
        freq = float(outcomes[mask].mean())
        rel += nb / n * (mean_p - freq) ** 2
        res += nb / n * (freq - base) ** 2
    return MurphyDecomposition(
        brier=brier_score(probs, outcomes),
        reliability=rel,
        resolution=res,
        uncertainty=base * (1 - base),
        base_rate=base,
    )


@dataclass(frozen=True)
class CalibrationBin:
    lo: float
    hi: float
    n: int
    mean_prob: float
    yes_rate: float
    ci_lo: float
    ci_hi: float


def calibration_table(probs: np.ndarray, outcomes: np.ndarray,
                      n_bins: int = 10) -> list[CalibrationBin]:
    """Per-bin mean forecast vs empirical YES rate with Wilson intervals."""
    probs = np.asarray(probs, dtype=float)
    outcomes = np.asarray(outcomes, dtype=float)
    bins = np.clip((probs * n_bins).astype(int), 0, n_bins - 1)
    out = []
    for b in range(n_bins):
        mask = bins == b
        nb = int(mask.sum())
        if nb == 0:
            continue
        k = int(outcomes[mask].sum())
        lo, hi = wilson_interval(k, nb)
        out.append(CalibrationBin(
            lo=b / n_bins, hi=(b + 1) / n_bins, n=nb,
            mean_prob=float(probs[mask].mean()),
            yes_rate=k / nb, ci_lo=lo, ci_hi=hi,
        ))
    return out


def strip_placeholder_prefix(ts: np.ndarray, prices: np.ndarray,
                             placeholder: float = 0.5,
                             spike_tolerance: float = 0.05
                             ) -> tuple[np.ndarray, np.ndarray]:
    """Remove Polymarket's exact-0.5 placeholder artifacts from a series.

    The prices-history endpoint emits exactly 0.5 (a) before the first
    CLOB trade, so never-traded markets are flat 0.5 forever, and (b) as
    isolated interior points on gap days (discovered when a 0.3 cent golf
    longshot printed a one-day 0.5 "price" and manufactured a 47 cent
    fake arbitrage). Rules, applied on the time-sorted series:

    1. Drop the leading run of exact placeholders.
    2. Drop any remaining exact placeholder whose surviving neighbors are
       all farther than spike_tolerance from 0.5. A genuine trade at
       0.50 sits amid nearby prices (sports moneylines) and survives;
       a placeholder spike between 0.003 and 0.002 does not.
    """
    order = np.argsort(ts)
    ts, prices = np.asarray(ts)[order], np.asarray(prices)[order]
    keep = prices != placeholder
    if not keep.any():
        return ts[:0], prices[:0]
    first_real = int(np.argmax(keep))
    ts, prices = ts[first_real:], prices[first_real:]

    # Placeholder points are not always exactly 0.5: on no-trade days the
    # endpoint emits the book midpoint, and an empty or one-sided book
    # midpoints NEAR 0.5 (0.4985 observed). Treat anything within 1.5
    # cents of 0.5 as a potential placeholder.
    is_ph = np.abs(prices - placeholder) <= 0.015
    if not is_ph.any():
        return ts, prices
    real_prices = prices[~is_ph]
    real_pos = np.flatnonzero(~is_ph)
    keep_mask = np.ones(len(prices), dtype=bool)
    for i in np.flatnonzero(is_ph):
        j = np.searchsorted(real_pos, i)
        neighbors = []
        if j > 0:
            neighbors.append(real_prices[j - 1])
        if j < len(real_prices):
            neighbors.append(real_prices[j])
        if neighbors and all(abs(v - prices[i]) > spike_tolerance
                             for v in neighbors):
            keep_mask[i] = False
    return ts[keep_mask], prices[keep_mask]


def price_at_horizon(ts: np.ndarray, prices: np.ndarray,
                     anchor_ts: int, horizon_seconds: int) -> float | None:
    """Last observed price at or before (anchor - horizon).

    Point-in-time discipline: only prices with timestamp at or before the
    snapshot moment are usable. Returns None when the market has no price
    history that early (e.g. it opened later than the horizon).
    """
    cutoff = anchor_ts - horizon_seconds
    ts = np.asarray(ts)
    mask = ts <= cutoff
    if not mask.any():
        return None
    idx = np.argmax(ts * mask)  # index of latest ts satisfying the mask
    return float(np.asarray(prices)[idx])
