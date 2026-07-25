# Results

Narrative findings, maintained by hand as phases complete. Every number
below comes from the generated tables in this directory
(`calibration_tables.md`, `divergence_tables.md`, `backtest_tables.md`),
rebuilt with `marketlens calibrate`, `marketlens diverge`, and
`marketlens backtest`. Figures live in `figures/`.

## Phase 3: Calibration, in plain English

Setup: for every sampled resolved market we took its price 24 hours
before close (and separately 7 days before close), using only data
available at that moment, and asked how often markets priced at X%
actually happened. Polymarket sample: 14,638 markets at the 24h horizon.
Kalshi: 11,010. Wilson 95% intervals throughout.

### 1. Both platforms are strikingly well calibrated overall

The reliability component of the Brier score (average squared gap between
what markets said and what happened, bucket by bucket; 0 is perfect) is
0.0001 for Polymarket and 0.0004 for Kalshi at the 24h horizon. For
context, always answering 50% would score 0.25 on the full Brier scale.
The interview sentence: "Polymarket contracts priced around 15 cents
resolved YES 15% of the time, contracts priced around 97 cents resolved
YES 98% of the time, and that diagonal pattern holds across every bucket
with tight confidence intervals" (see
`figures/calibration_polymarket_24h.png`).

### 2. The classic favorite-longshot bias is nearly gone

The textbook bias says longshots are overpriced and favorites
underpriced. At the 24h horizon:

- Polymarket longshots (mean implied 2.1%) resolved YES 1.8% of the time,
  CI [1.4%, 2.1%]. The implied price sits inside the interval: no
  significant bias.
- Polymarket favorites (implied 97.1%) resolved 98.2% [96.9%, 99.0%]:
  directionally the classic underpricing, not significant.
- Kalshi longshots (implied 3.0%) resolved 2.5% [2.1%, 3.0%]: the implied
  price sits at the interval's edge, a mild longshot overpricing worth
  about 0.5 probability points.
- Kalshi favorites (implied 96.7%) resolved 94.9% [92.9%, 96.3%]: the
  OPPOSITE of the classic pattern, and significant.

Honest summary: on 2026 short-horizon contracts the favorite-longshot
bias is at most half a percentage point where it exists at all. The
older literature studied longer-horizon, thinner, often
racetrack-style markets; modern liquid prediction markets have largely
arbitraged this away.

### 3. Kalshi's mid-to-high range runs slightly rich

Kalshi buckets from roughly 0.6 to 0.9 sit consistently 3 to 5 points
below the diagonal, significantly so: markets priced around 64 cents
resolved 60.1% (interval tops out at 64.2%), 75 cents resolved 69.8%
(tops out at 74.1%), and 96 cents resolved 94.2% (tops out at 95.7%).
Polymarket shows no comparable pattern. Two candidate explanations,
deliberately left open: a genuine tendency of Kalshi buyers to overpay
for likely-but-uncertain outcomes, or a residue of our quote handling,
since Kalshi days without trades contribute a bid/ask midpoint. Phase 5
uses bid and ask separately and finds real (if thin) edges buying the NO
side of Kalshi favorites, which is weak evidence for the first
explanation.

### 4. Markets sharpen as resolution approaches, cleanly

On the same set of markets scored at both horizons, so composition
cannot explain it: Polymarket's Brier improves from 0.1344 at 7 days to
0.1145 at 24 hours, with resolution (discrimination) rising 0.0705 to
0.0893. Kalshi improves 0.0766 to 0.0582, resolution 0.1032 to 0.1214.
Information flows into prices as events near, exactly as theory
predicts.

### 5. Thin markets are worse calibrated on Kalshi, not on Polymarket

Splitting each platform's 24h sample into volume terciles: Kalshi's thin
tercile has reliability 0.0029 against 0.0007 for the deep tercile, a
4x calibration-error gap supporting the "thin markets are worse
calibrated" hypothesis. Polymarket shows no such gradient (0.0014 thin
vs 0.0009 deep), consistent with its $1,000 volume floor having already
removed the truly dead markets. Note the Brier score itself RISES with
volume on both platforms; that is composition, not miscalibration: deep
markets are disproportionately sports games whose outcomes are genuinely
close to coin flips, so their irreducible uncertainty is higher.

### 6. Category cuts

Sports, the biggest slice on both platforms, is the best calibrated
(reliability 0.0001 Polymarket, 0.0006 Kalshi) despite the worst raw
Brier, again the composition effect. The worst calibration errors sit in
smaller categories: Kalshi economics (0.0036) and entertainment
(0.0035), Polymarket economics (0.0032). Kalshi's "mentions" markets
(will X say Y) have the highest Brier with decent calibration: genuinely
hard events, honestly priced.

## Phase 4: Divergence between platforms

For every verified matched pair we aligned both price series on calendar
days and computed spread = Polymarket minus Kalshi in probability points,
flipping inverse-orientation pairs to 1 - p first. 2,095 pairs had at
least two common days, 50,276 pair-days in total.

### 1. Disagreement is common but small

The pair-day weighted mean absolute spread is **4.2 points**. Spreads
exceed 2 points on 48% of pair-days, 5 points on 22%, and 10 points on
10%. A third of pairs (33%) average under 2 points of disagreement over
their whole life. The distribution is strongly right-skewed: most pairs
track each other closely, a minority diverge wildly.

![Spread distribution](figures/spread_distribution.png)

### 2. Gaps close fast: median half-life of one day

Defining a divergence event as |spread| crossing 5 points, and its
half-life as the days until the gap first falls to half its opening
level, we observed **3,641 resolved events with a median half-life of 1
day** and a 75th percentile of 2 days. Convergence is quick, which is
what makes the arbitrage question interesting: the window is short.

The half-life estimate is biased DOWNWARD by censoring: events still
open when a market closes never resolve and are excluded, so slow
convergences are systematically underrepresented. Daily price fidelity
also truncates anything faster than a day to exactly 1.

### 3. Kalshi appears to lead Polymarket, slightly

Across 493 pairs with at least 20 common days, the mean correlation of
daily price changes is 0.188 contemporaneously, 0.059 when Kalshi's move
precedes Polymarket's by a day, and 0.000 in the other direction. The
asymmetry is consistent (Kalshi leads), but both lagged correlations are
small next to the same-day figure, and daily data cannot resolve
intraday leadership. Treat this as suggestive, not established.

### 4. Case studies

The five annotated pairs in `figures/case_study_*.png` show the pattern
that summary statistics hide. The clearest is the San Antonio Spurs 2026
NBA championship market: over 316 common days the two venues track
within a mean 1.9 points for the entire regular season, then explode to
a 37 point maximum spread during the playoffs, when prices move many
times per day and daily snapshots on the two venues capture different
moments. Divergence is not a constant property of a pair; it is
concentrated in the fast-news periods when the price is moving anyway.

## Phase 5: Fee-adjusted arbitrage backtest

The economic question: when the platforms disagreed, was there free
money after costs? Strategy: for a verified same-proposition pair, buy
YES on one venue and NO on the other so exactly one leg pays $1 at
resolution. Enter on the first day the all-in cost (both taker fees, the
Kalshi leg at its closing ask or 1 minus bid, the Polymarket leg plus a
slippage haircut) drops below $1. Hold to resolution. Basis-risk pairs
are excluded because their $1 payout is not guaranteed.

### Results by slippage assumption

| Slippage (pts) | Opportunities | % of 2,144 tradable pairs | Mean edge | Median annualized |
|---|---|---|---|---|
| 0 | 1,154 | 53.8% | 5.1c | 50% |
| 1 | 919 | 42.9% | 5.9c | 76% |
| 2 | 778 | 36.3% | 6.5c | 101% |
| 3 | 706 | 32.9% | 6.5c | 114% |

Median edge at 1 point slippage is 3.2 cents on a roughly 95 cent
outlay, held a median 7 days. Total theoretical profit across all 919
trades is $54.51 per $1 of payout per trade, and **realized profit
computed from actual outcomes matches it exactly**: 913 of 919 trades
paid precisely $1, confirming both the arithmetic and the pair
verification.

Note the counterintuitive shape: mean edge and annualized return RISE as
the slippage assumption gets harsher. This is a selection effect, not a
paradox. Higher assumed slippage filters out the marginal opportunities
first, leaving only the largest gaps, which also tend to be the
shortest-lived. It is a useful reminder that "average return of surviving
trades" is the wrong headline metric under a changing filter; the
opportunity COUNT is the honest one, and it falls by 39% from 0 to 3
points of slippage.

### Why this is not a trading strategy

Three reasons the surviving edge is probably not real money, all
documented rather than assumed away:

1. **The edge lives where liquidity does not.** Sorting entered trades
   into volume quartiles, the median edge is **7.4 cents in the thinnest
   quartile against 1.3 cents in the deepest** (Spearman correlation
   between edge and log volume: -0.32). Polymarket publishes no
   historical order book, so "the price" is a last trade that may be
   good for $50, and the apparent profit is concentrated exactly where
   displayed prices least reflect executable size.
2. **The edges are small where they are plausible.** 39% of entered
   trades have an edge of 2 cents or less, within any reasonable
   uncertainty about fees, rounding, and execution timing.
3. **Capital is locked.** Median 7 days to resolution, but a quarter of
   trades sit for over a month. The eye-catching annualized figures come
   from dividing a few cents by a few days; a 3 cent edge held 7 days is
   3 cents, and the annualized framing flatters it.

The defensible claim is the market-microstructure one: **cross-platform
disagreements are frequent, mostly small, converge within about a day,
and the residual gaps that survive an honest fee model live in exactly
the places where execution is least trustworthy.** That is a market
efficiency finding, and it is what the data supports.

### 6 trades that did not pay $1

Six of 919 trades paid $0 or $2 instead of $1, meaning the two markets
resolved inconsistently. These are the residual verification errors that
survived Phase 2, and they are informative: five are "both teams to
score" soccer markets where the two venues attached the same generic
title to different fixtures, and one is a generically titled "Will
England win?" cricket market matched to a football World Cup group. They are
reported rather than removed. At 0.7% of trades, they also serve as an
outcome-based precision estimate for the verified pair set, which is
stricter than any text-similarity measure.
