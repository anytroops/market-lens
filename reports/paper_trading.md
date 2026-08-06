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
| polymarket | 58 | 3.01 pts | 7.26 pts | 14.71 pts |
| kalshi | 60 | 0.02 pts | 0.08 pts | 0.66 pts |

Kalshi's books are deep and tight; Polymarket's are not, which
is consistent with every other finding in the study. The
important part is the magnitude: **the backtest's 1 point
assumption understates real Polymarket execution cost at a
$200 order by roughly seven times**, and the sensitivity sweep
did not even extend that far.

Re-running the backtest at the measured levels rather than the
assumed ones:

| Slippage assumption | Opportunities | Share of tradable pairs |
|---|---|---|
| 1.0 pt (original default) | 906 | 42.9% |
| 3.01 pts (measured at $50) | 697 | 33.0% |
| 7.26 pts (measured at $200) | 474 | 22.4% |
| 14.71 pts (measured at $1000) | 260 | 12.3% |

So the headline arbitrage result does not merely weaken under
realistic execution, it roughly halves at a $200 trade and
falls by more than two thirds at $1000. Combined with the
capacity finding that the edge is concentrated in the thinnest
quartile, the honest conclusion is that the apparent edge is
an artifact of quoting rather than a tradable opportunity.

## Paper-trade signals

None yet. Signals require an open matched pair on both
venues at the same time, and the matched-pair opportunity
set turns out to be strongly seasonal: a single World Cup
produced 455 of the study's verified pairs. On a quiet day
Polymarket's near-dated book is UFC and Dota 2 while
Kalshi's is tennis sets and esports maps, which share no
propositions. Run `marketlens paper-trade` on a schedule so
the sample accumulates when the calendars do overlap.
