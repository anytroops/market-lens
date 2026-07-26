"""Single source of truth for turning a stored price row into a probability.

Both platforms need care, for different reasons.

Kalshi candlesticks carry a last-trade price that can be STALE: the field
persists the most recent trade even when it is days old and the book has
moved far away. Measured on this dataset, 2.2% of Kalshi rows that have
both a trade and a book show a trade outside the book by more than 5
points, and 0.12% by more than 50 points (e.g. a market quoted 8 to 14
cents reporting a 96 cent last trade). Taken at face value those prints
manufacture enormous fake divergences, so a trade that contradicts the
same-day book is discarded in favour of the book.

Polymarket has no book at all, so its price is used as-is; its own
artifact (a placeholder near 0.50 before the first trade) is handled
separately by strip_placeholder_prefix.
"""

from __future__ import annotations

MAX_SPREAD = 0.20
TRADE_TOLERANCE = 0.05


def usable_price(price: float | None, bid: float | None, ask: float | None,
                 max_spread: float = MAX_SPREAD,
                 tolerance: float = TRADE_TOLERANCE) -> float | None:
    """Best probability estimate for one market-day, or None if unusable.

    Rules, in order:
    1. A trade with no book at all (Polymarket) is trusted, since there is
       nothing to check it against.
    2. Otherwise the day needs a two-sided book tighter than max_spread.
       A wide book means there is no consensus to read: an observed
       Kalshi day with bid 0.00 and ask 0.97 recorded a 9-contract trade
       at 0.97, which is one person lifting a lone resting order, not a
       97% probability. Days like that are dropped rather than believed.
    3. Within a tight book, a trade close to it is the best estimate.
    4. A trade that contradicts a tight book is stale, so the midpoint
       is used instead.
    """
    if price is not None and (bid is None or ask is None):
        return price

    has_book = (bid is not None and ask is not None and ask >= bid)
    if not has_book or (ask - bid) > max_spread:
        return None

    midpoint = (bid + ask) / 2.0
    if price is None:
        return midpoint
    if bid - tolerance <= price <= ask + tolerance:
        return price
    return midpoint  # stale print contradicting a tight book
