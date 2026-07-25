"""Does anything beat the market price? (Phase 6, deliberately small)

Question: does a simple model using extra features predict resolution
better than the market price alone?

Design note that makes the comparison honest: logistic regression is
linear in LOG-ODDS, so the price enters as logit(price), not as a raw
probability. Under that parameterization the price-only baseline is
exactly the model with coefficient 1.0 on logit(price) and intercept 0.
A fitted coefficient near 1.0 with near-zero coefficients elsewhere is
direct evidence that the market price already contains the information;
a coefficient below 1.0 would mean prices are systematically too
confident, above 1.0 too timid.

Evaluation is a temporal split (train on markets resolving before a cut
date, test after), because a random split would leak information across
time and flatter the model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-6


def clip_probs(p: np.ndarray) -> np.ndarray:
    """Keep probabilities strictly inside (0, 1) so logs stay finite."""
    return np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)


def logit(p: np.ndarray) -> np.ndarray:
    """Log-odds transform, the natural scale for probability forecasts."""
    p = clip_probs(p)
    return np.log(p / (1 - p))


def log_loss(y_true: np.ndarray, p: np.ndarray) -> float:
    """Mean negative log likelihood of the observed outcomes.

    Lower is better. A forecaster who always says 0.5 scores ln(2), about
    0.693, which is the reference point for "knows nothing".
    """
    y = np.asarray(y_true, dtype=float)
    p = clip_probs(p)
    if y.size == 0:
        raise ValueError("empty input")
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def pointwise_log_loss(y_true: np.ndarray, p: np.ndarray) -> np.ndarray:
    """Per-observation negative log likelihood (the log_loss summands)."""
    y = np.asarray(y_true, dtype=float)
    p = clip_probs(p)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def paired_loss_difference(y_true: np.ndarray, p_a: np.ndarray,
                           p_b: np.ndarray) -> dict:
    """Is model A's log loss really lower than model B's, or is it noise?

    Compares the two models on the SAME observations, so the paired
    differences remove the effect of which markets happened to be easy.
    Returns the mean difference (positive when A is worse), its standard
    error, and the t statistic. Beating a benchmark by less than about
    two standard errors is not evidence of skill.
    """
    d = pointwise_log_loss(y_true, p_a) - pointwise_log_loss(y_true, p_b)
    n = d.size
    if n < 2:
        raise ValueError("need at least two observations")
    mean = float(d.mean())
    se = float(d.std(ddof=1) / np.sqrt(n))
    return {"mean_difference": mean, "std_error": se,
            "t_stat": (mean / se if se > 0 else float("nan")), "n": int(n)}


def temporal_split(df: pd.DataFrame, date_col: str,
                   test_fraction: float = 0.3) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split by time: earliest (1 - f) of rows train, latest f test.

    The cut lands on a date boundary, so no single resolution date spans
    both sides and there is no leakage across the split.
    """
    if df.empty:
        return df, df
    ordered = df.sort_values(date_col)
    cut = ordered[date_col].quantile(1 - test_fraction)
    train = ordered[ordered[date_col] <= cut]
    test = ordered[ordered[date_col] > cut]
    return train, test


def momentum(price_now: float, price_earlier: float | None) -> float:
    """Change in log-odds over the trailing window, 0 when unavailable.

    Expressed in log-odds rather than raw points so a move from 0.01 to
    0.02 (a doubling) counts as more than a move from 0.50 to 0.51.
    """
    if price_earlier is None or not np.isfinite(price_earlier):
        return 0.0
    return float(logit(np.array([price_now]))[0]
                 - logit(np.array([price_earlier]))[0])
