"""Fee-adjusted cross-platform arbitrage backtest (Phase 5).

Strategy (deliberately simple, per spec): for a verified same-proposition
pair at day t, buying YES on one venue and NO on the other locks in a $1
payout at resolution. If the combined cost including fees and slippage is
below 1 minus an edge threshold, that is a theoretical arbitrage. Enter at
the FIRST qualifying day per pair, hold both legs to resolution.

Execution realism:
- Kalshi legs price at the day's closing quotes: YES buys at yes_ask, NO
  buys at 1 - yes_bid. Days without both quotes are not tradable.
- Polymarket has no historical book, so its leg pays last price plus a
  configurable slippage haircut (sensitivity sweeps 0 to 3 points).
- Fees per config.yaml: both platforms charge takers
  rate * price * (1 - price) per contract; the Kalshi rate is flat, the
  Polymarket rate depends on category.
- Point-in-time discipline: the entry decision at day t uses only that
  day's observations. No lookahead.
- Basis-risk pairs are excluded: their $1 combined payout is not
  guaranteed, which is the definition of basis risk.

Honesty check: realized P&L is also computed from the two markets' ACTUAL
outcomes. For a correctly verified pair exactly one leg pays and realized
equals theoretical; a divergence between the two flags a bad pair rather
than free money.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

DAYS_PER_YEAR = 365.0


def taker_fee(rate: float, price: float) -> float:
    """Fee per contract: rate * P * (1 - P)."""
    return rate * price * (1.0 - price)


@dataclass(frozen=True)
class LegBook:
    """One day's tradable quotes for a pair, YES-side probabilities."""
    pm_price: float
    k_yes_ask: float
    k_yes_bid: float


@dataclass(frozen=True)
class Entry:
    direction: str  # 'pm_yes' buys PM YES + Kalshi NO; 'k_yes' the reverse
    cost: float     # all-in cost of $1 guaranteed payout
    edge: float     # 1 - cost


def best_entry(book: LegBook, pm_fee_rate: float, kalshi_fee_rate: float,
               slippage_points: float) -> Entry:
    """Cheapest way to lock in $1, all-in, at one day's quotes."""
    slip = slippage_points / 100.0

    pm_yes = min(1.0, book.pm_price + slip)
    k_no = 1.0 - book.k_yes_bid  # buying NO lifts the NO ask = 1 - yes bid
    cost_a = (pm_yes + taker_fee(pm_fee_rate, pm_yes)
              + k_no + taker_fee(kalshi_fee_rate, k_no))

    k_yes = book.k_yes_ask
    pm_no = min(1.0, (1.0 - book.pm_price) + slip)
    cost_b = (k_yes + taker_fee(kalshi_fee_rate, k_yes)
              + pm_no + taker_fee(pm_fee_rate, pm_no))

    if cost_a <= cost_b:
        return Entry("pm_yes", cost_a, 1.0 - cost_a)
    return Entry("k_yes", cost_b, 1.0 - cost_b)


@dataclass(frozen=True)
class Trade:
    pm_id: str
    kalshi_id: str
    entry_day: object
    direction: str
    cost: float
    edge: float
    days_held: float
    annualized: float
    realized_payout: float
    realized_pnl: float


def realized_payout(direction: str, pm_outcome: str, k_outcome: str) -> float:
    """Dollars actually collected at resolution given real outcomes.

    For a correct pair this is exactly 1. It differs only when the two
    markets resolved differently (a bad or basis-risk pair).
    """
    if direction == "pm_yes":
        return float(pm_outcome == "YES") + float(k_outcome == "NO")
    return float(k_outcome == "YES") + float(pm_outcome == "NO")


def backtest_pair(days: pd.DataFrame, pm_outcome: str, k_outcome: str,
                  pm_fee_rate: float, kalshi_fee_rate: float,
                  slippage_points: float, edge_threshold: float,
                  resolve_day, pm_id: str = "", kalshi_id: str = ""
                  ) -> Trade | None:
    """First qualifying entry for one pair, held to resolution.

    days: DataFrame indexed by date with columns pm, k_ask, k_bid.

    Entry guard: the Polymarket leg has no historical book, so a price
    that jumped more than 25 points against the previous observation
    cannot be distinguished from a stale or empty-book artifact and never
    triggers an entry. The first observation of a pair is likewise not
    trusted on its own.
    """
    prev_pm = None
    for day, row in days.iterrows():
        if pd.isna(row["pm"]) or pd.isna(row["k_ask"]) or pd.isna(row["k_bid"]):
            continue
        pm_ok = prev_pm is not None and abs(row["pm"] - prev_pm) <= 0.25
        prev_pm = row["pm"]
        if not pm_ok:
            continue
        book = LegBook(pm_price=row["pm"], k_yes_ask=row["k_ask"],
                       k_yes_bid=row["k_bid"])
        entry = best_entry(book, pm_fee_rate, kalshi_fee_rate, slippage_points)
        if entry.edge <= edge_threshold:
            continue
        held = max((resolve_day - day).days, 1)
        payout = realized_payout(entry.direction, pm_outcome, k_outcome)
        per_trade_return = entry.edge / entry.cost
        return Trade(
            pm_id=pm_id, kalshi_id=kalshi_id, entry_day=day,
            direction=entry.direction, cost=entry.cost, edge=entry.edge,
            days_held=held,
            annualized=per_trade_return * DAYS_PER_YEAR / held,
            realized_payout=payout,
            realized_pnl=payout - entry.cost,
        )
    return None
