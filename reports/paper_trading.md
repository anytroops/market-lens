# Paper Trading Forward Test

Read-only forward test of the Phase 5 arbitrage rule against
live order books. No orders are placed. Each signal records the
edge at the touch, which is what the historical backtest could
see, and the edge after actually walking the book for a given
trade size.

## Measured execution cost

The historical backtest could not see depth, so it applied a
flat slippage haircut to the Polymarket leg and swept it from 0
to 3 points. These are the real numbers from live books.

| Platform | Books | Avg slippage vs touch at $50 | at $200 | at $1000 |
|---|---|---|---|---|
| polymarket | 116 | 2.78 pts | 6.55 pts | 13.48 pts |
| kalshi | 120 | 0.02 pts | 0.08 pts | 0.60 pts |

Those averages hide the shape, and the shape is the finding.
Polymarket slippage is not uniformly high: the MEDIAN market
costs about 0.4 points at $200, while the mean is dragged to
roughly 7 by a thin tail. Splitting by how much is actually
resting on the book:

| Polymarket book depth | Median resting | Median slippage at $200 |
|---|---|---|
| thinnest quartile | $3,379 | 20.43 pts |
| middle half | $156,649 | 0.10 pts |
| deepest quartile | $706,259 | 0.00 pts |

Slippage is effectively zero in liquid Polymarket markets
and enormous in thin ones. Repeat observations of the same
market show a within-market standard deviation of about
0.02 points, so this is a stable property of each book
rather than measurement noise.

**This is what closes the arbitrage question.** The
backtest already found the edge was six times larger in the
thinnest volume quartile than the deepest. The depth data
shows execution costs about 20 points in exactly those thin
markets and nothing in the liquid ones. A 3 to 7 cent edge
that only exists where crossing the spread costs 20 cents is
not an opportunity, and the two measurements were taken
independently.

Re-running the backtest with the mean measured slippage rather
than the assumed 1 point:

| Slippage assumption | Opportunities | Share of tradable pairs |
|---|---|---|
| 1.0 pt (original default) | 906 | 42.9% |
| 3.01 pts (measured mean at $50) | 697 | 33.0% |
| 7.26 pts (measured mean at $200) | 474 | 22.4% |
| 14.71 pts (measured mean at $1000) | 260 | 12.3% |

Even that understates the problem, because a flat haircut
applied to every pair is the wrong model: the real cost is near
zero for most markets and catastrophic for the thin ones the
strategy actually selects.

## Paper-trade signals

None yet. Signals require an open matched pair on both
venues at the same time, and the matched-pair opportunity
set turns out to be strongly seasonal: a single World Cup
produced 455 of the study's verified pairs. On a quiet day
Polymarket's near-dated book is UFC and Dota 2 while
Kalshi's is tennis sets and esports maps, which share no
propositions. Run `marketlens paper-trade` on a schedule so
the sample accumulates when the calendars do overlap.
