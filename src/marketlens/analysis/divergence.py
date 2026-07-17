"""Divergence analysis for verified matched pairs (Phase 4).

Concepts:
- spread(t) = polymarket price minus kalshi price, in probability points
  (0 to 100 scale), after flipping the Kalshi series to 1 - p for pairs
  verified as inverse orientation.
- Alignment is on calendar days (UTC). Both platforms were ingested at
  daily fidelity; each market's last observation per day is used, and
  only days where BOTH platforms have an observation enter the spread.
- Convergence half-life: when |spread| first reaches the event threshold
  (default 5 points), record the days until |spread| first drops to half
  the entry level. Median across events is the empirical half-life. This
  is the radioactive decay analogy: the time for the remaining gap to
  shrink by half.

All functions are pure and unit-tested.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

POINTS = 100.0


def daily_series(ts: np.ndarray, prices: np.ndarray) -> pd.Series:
    """Collapse an intraday-or-daily price series to one value per UTC day.

    Takes the LAST observation of each day, indexed by date.
    """
    if len(ts) == 0:
        return pd.Series(dtype=float)
    idx = pd.to_datetime(np.asarray(ts, dtype="int64"), unit="s", utc=True)
    s = pd.Series(np.asarray(prices, dtype=float), index=idx).sort_index()
    return s.groupby(s.index.date).last()


def align_pair(pm: pd.Series, kalshi: pd.Series,
               orientation: str = "same") -> pd.DataFrame:
    """Join two daily series on common days and compute the spread.

    Returns a DataFrame with columns pm, kalshi, spread (probability
    points, pm minus kalshi). Inverse pairs flip the Kalshi series to
    1 - p so both series price the same proposition.
    """
    if orientation == "inverse":
        kalshi = 1.0 - kalshi
    df = pd.concat({"pm": pm, "kalshi": kalshi}, axis=1, join="inner").dropna()
    df["spread"] = (df["pm"] - df["kalshi"]) * POINTS
    return df


@dataclass(frozen=True)
class SpreadStats:
    n_days: int
    mean_abs: float
    max_abs: float
    pct_gt2: float
    pct_gt5: float
    pct_gt10: float


def spread_stats(spread: pd.Series) -> SpreadStats | None:
    """Summary statistics of a spread series in probability points."""
    a = spread.abs()
    if len(a) == 0:
        return None
    return SpreadStats(
        n_days=int(len(a)),
        mean_abs=float(a.mean()),
        max_abs=float(a.max()),
        pct_gt2=float((a > 2).mean() * 100),
        pct_gt5=float((a > 5).mean() * 100),
        pct_gt10=float((a > 10).mean() * 100),
    )


def half_life_events(spread: pd.Series, threshold: float = 5.0) -> list[float]:
    """Days from each divergence event opening until the gap first halves.

    An event opens when |spread| crosses the threshold from below (or the
    series starts above it). It resolves when |spread| first drops to at
    most half the entry level; the elapsed days are recorded. Events still
    open at the end of the series are censored and excluded, which biases
    the estimate DOWNWARD (fast convergences are observed, slow ones can
    fall off the end); the write-up states this.
    """
    a = spread.abs().to_numpy(dtype=float)
    days = np.arange(len(a), dtype=float)
    out: list[float] = []
    in_event = False
    entry_level = 0.0
    entry_day = 0.0
    for i in range(len(a)):
        if not in_event:
            if a[i] >= threshold and (i == 0 or a[i - 1] < threshold):
                in_event = True
                entry_level = a[i]
                entry_day = days[i]
        else:
            if a[i] <= entry_level / 2:
                out.append(days[i] - entry_day)
                in_event = False
            elif a[i] >= threshold and a[i] > entry_level:
                entry_level = a[i]  # gap widened: measure from the peak
                entry_day = days[i]
    return out


def lead_lag_correlation(df: pd.DataFrame, max_lag: int = 2) -> dict[int, float]:
    """Correlation of daily CHANGES at small lags.

    Positive lag k means Polymarket's move today correlates with Kalshi's
    move k days later (Polymarket leads). Uses only pairs' common days;
    NaN when there are too few observations.
    """
    dpm = df["pm"].diff()
    dk = df["kalshi"].diff()
    out = {}
    for lag in range(-max_lag, max_lag + 1):
        shifted = dk.shift(-lag)
        valid = dpm.notna() & shifted.notna()
        if valid.sum() < 3 or dpm[valid].std() == 0 or shifted[valid].std() == 0:
            out[lag] = float("nan")
        else:
            out[lag] = float(dpm[valid].corr(shifted[valid]))
    return out
