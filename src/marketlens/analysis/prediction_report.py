"""Phase 6 orchestration: features -> temporal split -> model vs price.

Feature frame is built at the 24h horizon, one row per resolved market
with a usable price snapshot, using only information available at the
snapshot moment.
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from marketlens.analysis import calibration as cal
from marketlens.analysis import prediction as pr
from marketlens.matching.matcher import category_bucket

log = logging.getLogger(__name__)

HORIZON_SECONDS = 86400
MOMENTUM_WINDOW = 7 * 86400
MAX_QUOTE_SPREAD = 0.20
SEED = 42


def build_feature_frame(conn: sqlite3.Connection) -> pd.DataFrame:
    """One row per resolved market: features known at the snapshot, plus outcome."""
    rows = []
    for platform in ("polymarket", "kalshi"):
        markets = {
            mid: (close_ts, outcome, category, volume)
            for mid, close_ts, outcome, category, volume in conn.execute(
                """SELECT market_id, close_ts, outcome, category, volume
                   FROM headline_markets WHERE platform = ?""", (platform,))
        }
        series: dict[str, list[tuple[int, float]]] = defaultdict(list)
        for mid, ts, price, bid, ask in conn.execute(
                "SELECT market_id, ts, price, bid, ask FROM prices "
                "WHERE platform = ?", (platform,)):
            if price is None:
                if bid is None or ask is None or (ask - bid) > MAX_QUOTE_SPREAD:
                    continue
                price = (bid + ask) / 2.0
            series[mid].append((ts, price))

        for mid, points in series.items():
            meta = markets.get(mid)
            if meta is None:
                continue
            close_ts, outcome, category, volume = meta
            points.sort()
            ts = np.array([p[0] for p in points])
            px = np.array([p[1] for p in points])
            if platform == "polymarket":
                ts, px = cal.strip_placeholder_prefix(ts, px)
            if len(ts) == 0:
                continue
            anchor = int(dt.datetime.fromisoformat(
                close_ts.replace("Z", "+00:00")).timestamp())
            p_now = cal.price_at_horizon(ts, px, anchor, HORIZON_SECONDS)
            if p_now is None:
                continue
            p_prev = cal.price_at_horizon(
                ts, px, anchor, HORIZON_SECONDS + MOMENTUM_WINDOW)
            lifetime_days = (anchor - int(ts[0])) / 86400.0
            rows.append({
                "platform": platform,
                "market_id": mid,
                "resolve_date": pd.Timestamp(close_ts.replace("Z", "+00:00")),
                "price": p_now,
                "logit_price": float(pr.logit(np.array([p_now]))[0]),
                "momentum_7d": pr.momentum(p_now, p_prev),
                "has_momentum": float(p_prev is not None),
                "log_volume": float(np.log1p(volume or 0.0)),
                "lifetime_days": lifetime_days,
                "bucket": category_bucket(platform, category),
                "outcome": 1 if outcome == "YES" else 0,
            })
    df = pd.DataFrame(rows)
    log.info("feature frame: %d markets", len(df))
    return df


# log_volume is DELIBERATELY excluded. markets.volume is the market's
# LIFETIME volume as recorded at ingestion, which is after resolution, so
# it is not knowable at the 24h snapshot. Including it produced the
# project's only apparent "beat the market" result (log-loss gain 0.00306,
# t = 6.14, essentially the entire gain of the full model) because markets
# that resolve YES dramatically attract late volume. That is textbook
# lookahead bias, caught by asking which single feature carried the gain.
# A point-in-time volume feature would need cumulative volume up to the
# snapshot, which Kalshi candlesticks support and Polymarket does not.
FEATURES = ["logit_price", "momentum_7d", "has_momentum", "lifetime_days",
            "bucket", "platform"]


def design_matrix(df: pd.DataFrame, columns: list[str] | None = None):
    """Numeric design matrix with category and platform dummies."""
    X = pd.get_dummies(
        df[FEATURES], columns=["bucket", "platform"], drop_first=True,
        dtype=float)
    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0.0)
    return X


def run(conn: sqlite3.Connection, test_fraction: float = 0.3) -> dict:
    """Fit the feature model, compare against the price-only baseline."""
    df = build_feature_frame(conn)
    train, test = pr.temporal_split(df, "resolve_date", test_fraction)
    if len(test) < 200 or len(train) < 500:
        raise ValueError("not enough data for a temporal split")

    X_train = design_matrix(train)
    X_test = design_matrix(test, columns=list(X_train.columns))
    y_train = train["outcome"].to_numpy()
    y_test = test["outcome"].to_numpy()

    model = LogisticRegression(max_iter=2000, C=1.0, random_state=SEED)
    model.fit(X_train.to_numpy(), y_train)
    p_model = model.predict_proba(X_test.to_numpy())[:, 1]
    p_price = test["price"].to_numpy()

    # Ablation: a model with ONLY logit(price) is a pure recalibration of
    # the market (a fitted slope and intercept, no new information). The
    # gap between it and the full model is what the extra features add.
    recal = LogisticRegression(max_iter=2000, C=1.0, random_state=SEED)
    recal.fit(X_train[["logit_price"]].to_numpy(), y_train)
    p_recal = recal.predict_proba(X_test[["logit_price"]].to_numpy())[:, 1]

    coefs = dict(zip(X_train.columns, model.coef_[0].round(4)))
    paired = pr.paired_loss_difference(y_test, p_price, p_model)
    paired_recal = pr.paired_loss_difference(y_test, p_price, p_recal)
    paired_features = pr.paired_loss_difference(y_test, p_recal, p_model)
    return {
        "recal_log_loss": pr.log_loss(y_test, p_recal),
        "recal_brier": cal.brier_score(p_recal, y_test),
        "recal_gain": paired_recal["mean_difference"],
        "recal_t": paired_recal["t_stat"],
        "features_gain": paired_features["mean_difference"],
        "features_t": paired_features["t_stat"],
        "paired_mean_gain": paired["mean_difference"],
        "paired_std_error": paired["std_error"],
        "paired_t_stat": paired["t_stat"],
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "train_end": str(train["resolve_date"].max().date()),
        "test_start": str(test["resolve_date"].min().date()),
        "baseline_log_loss": pr.log_loss(y_test, p_price),
        "model_log_loss": pr.log_loss(y_test, p_model),
        "baseline_brier": cal.brier_score(p_price, y_test),
        "model_brier": cal.brier_score(p_model, y_test),
        "intercept": float(model.intercept_[0]),
        "coef_logit_price": float(coefs.get("logit_price", float("nan"))),
        "coefficients": coefs,
        "test_base_rate": float(y_test.mean()),
        "always_base_rate_log_loss": pr.log_loss(
            y_test, np.full_like(p_price, y_test.mean())),
    }
