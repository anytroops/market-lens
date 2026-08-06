"""Order book depth model.

This is the piece the historical backtest could not have. Both platforms
publish live depth, so instead of assuming a slippage haircut we can ask
the question the backtest could only guess at: at what average price
could you actually buy N dollars of this contract right now?

Conventions. A book is expressed as a YES-side ladder in probability
units: `bids` are resting orders you could sell YES into (best first,
descending price) and `asks` are orders you could buy YES from (best
first, ascending price). Sizes are in contracts.

Platform quirks folded in here so callers never see them:
- Kalshi publishes two bid ladders, `yes_dollars` and `no_dollars`. A
  resting NO bid at q is an offer to sell YES at 1 - q, so the YES ask
  ladder is the NO ladder mirrored.
- Polymarket publishes bids and asks directly, but ascending by price in
  both cases, so the bid side needs reversing to be best-first.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Level:
    price: float
    size: float  # contracts


@dataclass(frozen=True)
class Book:
    """One side-agnostic snapshot, always expressed in YES probability."""
    bids: list[Level]  # best (highest) first: you can SELL yes into these
    asks: list[Level]  # best (lowest) first: you can BUY yes from these

    @property
    def best_bid(self) -> float | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> float | None:
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> float | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid


def _levels(pairs, reverse: bool) -> list[Level]:
    out = [Level(float(p), float(s)) for p, s in pairs if float(s) > 0]
    out.sort(key=lambda l: l.price, reverse=reverse)
    return out


def parse_kalshi_book(payload: dict) -> Book:
    """Kalshi orderbook payload to a YES-side book.

    `yes_dollars` are YES bids. `no_dollars` are NO bids, each of which is
    an offer to sell YES at 1 - price, so mirroring them yields the YES
    ask ladder.
    """
    ob = (payload or {}).get("orderbook_fp") or (payload or {}).get("orderbook") or {}
    yes = ob.get("yes_dollars") or ob.get("yes") or []
    no = ob.get("no_dollars") or ob.get("no") or []
    bids = _levels(yes, reverse=True)
    asks = _levels([[1.0 - float(p), s] for p, s in no], reverse=False)
    return Book(bids=bids, asks=asks)


def parse_polymarket_book(payload: dict) -> Book:
    """Polymarket CLOB book payload to a YES-side book."""
    p = payload or {}
    bids = _levels([(b["price"], b["size"]) for b in p.get("bids") or []],
                   reverse=True)
    asks = _levels([(a["price"], a["size"]) for a in p.get("asks") or []],
                   reverse=False)
    return Book(bids=bids, asks=asks)


@dataclass(frozen=True)
class Fill:
    """Result of walking the book for a target notional."""
    filled_notional: float   # dollars actually fillable
    contracts: float
    vwap: float | None       # average price paid per contract
    levels_consumed: int
    complete: bool           # True when the full target was available


def walk_book(levels: list[Level], target_notional: float) -> Fill:
    """Consume the ladder until target_notional dollars are spent.

    Returns the volume-weighted average price actually achievable, which
    is the number the backtest's flat slippage assumption was standing in
    for. A partial fill (complete=False) means the book is thinner than
    the trade you wanted.
    """
    if target_notional <= 0:
        return Fill(0.0, 0.0, None, 0, True)
    spent = 0.0
    contracts = 0.0
    used = 0
    for lvl in levels:
        if lvl.price <= 0:
            continue
        level_notional = lvl.price * lvl.size
        remaining = target_notional - spent
        if level_notional >= remaining:
            take = remaining / lvl.price
            spent += remaining
            contracts += take
            used += 1
            return Fill(spent, contracts, spent / contracts, used, True)
        spent += level_notional
        contracts += lvl.size
        used += 1
    vwap = (spent / contracts) if contracts > 0 else None
    return Fill(spent, contracts, vwap, used, False)


def executable_cost(book: Book, notional: float) -> float | None:
    """VWAP to buy `notional` dollars of YES, or None if the book cannot fill it.

    This replaces the backtest's flat slippage haircut with the real
    number, and returning None for an unfillable size is the point: it
    makes "this edge had no capacity" an explicit outcome rather than an
    invisible assumption.
    """
    fill = walk_book(book.asks, notional)
    return fill.vwap if fill.complete else None


def no_ask_ladder(book: Book) -> list[Level]:
    """The ladder for BUYING NO, derived from the YES bids.

    Buying NO at q is the same trade as selling YES at 1 - q, so every
    resting YES bid is an offer of NO at one minus its price. Because the
    YES bids are ordered best (highest) first, the mirrored prices come
    out ascending, which is already best-first for a buyer.
    """
    return [Level(1.0 - lvl.price, lvl.size) for lvl in book.bids]


def executable_no_cost(book: Book, notional: float) -> float | None:
    """VWAP to buy `notional` dollars of NO, or None if unfillable."""
    fill = walk_book(no_ask_ladder(book), notional)
    return fill.vwap if fill.complete else None


def slippage_points(book: Book, notional: float) -> float | None:
    """How many probability points worse than the touch a real fill would be."""
    vwap = executable_cost(book, notional)
    if vwap is None or book.best_ask is None:
        return None
    return (vwap - book.best_ask) * 100.0
