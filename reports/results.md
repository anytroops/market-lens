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
Kalshi: 10,643. Wilson 95% intervals throughout.

### 1. Both platforms are strikingly well calibrated overall

The reliability component of the Brier score (average squared gap between
what markets said and what happened, bucket by bucket; 0 is perfect) is
0.0001 for Polymarket and 0.0002 for Kalshi at the 24h horizon. For
context, always answering 50% would score 0.25 on the full Brier scale.
The interview sentence: "Polymarket contracts priced around 15 cents
resolved YES 15% of the time, contracts priced around 97 cents resolved
YES 98% of the time, and that diagonal pattern holds across every bucket
with tight confidence intervals" (see
`figures/calibration_polymarket_24h.png`).

### 2. The favorite-longshot bias is absent on Polymarket, small but real on Kalshi

The textbook bias says longshots are overpriced and favorites
underpriced. At the 24h horizon:

- Polymarket longshots (mean implied 2.1%) resolved YES 1.8% of the time,
  CI [1.4%, 2.1%]. The implied price sits inside the interval: no
  significant bias.
- Polymarket favorites (implied 97.1%) resolved 98.2% [96.9%, 99.0%]:
  directionally the classic underpricing, not significant.
- Kalshi longshots (implied 3.1%) resolved 2.3% [1.9%, 2.7%]. The implied
  price sits above the whole interval, so this is a **significant
  longshot overpricing of about 0.8 percentage points**, the classic
  effect.
- Kalshi favorites (implied 96.7%) resolved 97.4% [95.8%, 98.4%]:
  directionally classic, not significant.

Honest summary: the direction of the textbook bias is right on Kalshi and
statistically detectable in the longshot tail, but the magnitude is under
one percentage point, an order of magnitude smaller than the racetrack
literature. Polymarket shows no significant bias in either tail. An
earlier version of this analysis reported the opposite sign on Kalshi
favorites; that was an artifact of stale last-trade prints, described in
the data-quality note below.

### 3. A finding that did not survive better data cleaning

An earlier run reported that Kalshi's 0.6 to 0.9 buckets sat 3 to 5
points below the diagonal, significantly, and that its favorites were
overpriced. Both effects disappeared once stale last-trade prints were
removed. In the corrected data those buckets sit inside their confidence
intervals: markets priced around 64 cents resolve 61.4% (interval reaches
65.6%), 75 cents resolve 72.1% (reaches 76.4%), and 85 cents resolve
84.8% against an implied 84.5%.

What survives is narrower and cleaner: the longshot bucket and the 0.2 to
0.3 bucket are both significantly rich on Kalshi (implied 24.5% resolving
21.4%, interval reaching 24.2%). This is worth stating plainly because
the retracted version was the more interesting claim. A finding that
evaporates when a data artifact is fixed was never a finding.

**Data-quality note: stale Kalshi prints.** Kalshi's daily candlesticks
carry a last-trade price that persists even when the trade is old and the
book has moved far away. Measured here, 2.2% of Kalshi rows with both a
trade and a book had the trade more than 5 points outside the book, and
0.12% more than 50 points outside: one market quoted 8 to 14 cents
reported a 96 cent last trade. A related case is a trade printing at the
ask of an essentially empty book (bid 0.00, ask 0.97, with a 9-lot
trading at 0.97), which is one person lifting a lone resting order rather
than a 97% consensus. Both are now rejected by a single shared rule in
`analysis/prices.py`: a Kalshi day is usable only if it has a two-sided
book tighter than 20 points, and within that book a trade is preferred
only when consistent with the quotes. This was found by inspecting a
case-study chart showing a 91 point one-day divergence that was too large
to be real.

### 4. Markets sharpen as resolution approaches, cleanly

On the same set of markets scored at both horizons, so composition
cannot explain it: Polymarket's Brier improves from 0.1344 at 7 days to
0.1145 at 24 hours, with resolution (discrimination) rising 0.0705 to
0.0893. Kalshi improves 0.0709 to 0.0538, resolution 0.1076 to 0.1254.
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
flipping inverse-orientation pairs to 1 - p first. 2,022 pairs had at
least two common days, 49,340 pair-days in total.

### 1. Disagreement is common but small

The pair-day weighted mean absolute spread is **3.9 points**. Spreads
exceed 2 points on 48% of pair-days, 5 points on 21%, and 10 points on
9%. A third of pairs (33%) average under 2 points of disagreement over
their whole life. The distribution is strongly right-skewed: most pairs
track each other closely, a minority diverge wildly.

![Spread distribution](figures/spread_distribution.png)

### 2. Gaps close fast: median half-life of one day

Defining a divergence event as |spread| crossing 5 points, and its
half-life as the days until the gap first falls to half its opening
level, we observed **3,414 resolved events with a median half-life of 1
day** and a 75th percentile of 2 days. Convergence is quick, which is
what makes the arbitrage question interesting: the window is short.

The half-life estimate is biased DOWNWARD by censoring: events still
open when a market closes never resolve and are excluded, so slow
convergences are systematically underrepresented. Daily price fidelity
also truncates anything faster than a day to exactly 1.

### 3. Kalshi appears to lead Polymarket, slightly

Across 493 pairs with at least 20 common days, the mean correlation of
daily price changes is 0.217 contemporaneously, 0.055 when Kalshi's move
precedes Polymarket's by a day, and 0.006 in the other direction. The
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

| Slippage (pts) | Opportunities | % of 2,095 tradable pairs | Mean edge | Median annualized |
|---|---|---|---|---|
| 0 | 1,128 | 53.8% | 5.1c | 50% |
| 1 | 899 | 42.9% | 5.9c | 74% |
| 2 | 762 | 36.4% | 6.4c | 95% |
| 3 | 690 | 32.9% | 6.5c | 107% |

Median edge at 1 point slippage is 3.2 cents on a roughly 95 cent
outlay, held a median 7 days. Total theoretical profit across all 899
trades is $52.96, and **realized profit computed from actual outcomes
matches it exactly**, because **every one of the 899 trades paid
precisely $1**. That is the strongest available confirmation that both
the cost arithmetic and the pair verification are correct: if any pair
had been mismatched, its two legs would have resolved inconsistently and
paid $0 or $2.

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
   into volume quartiles, the median edge falls monotonically: **7.5
   cents in the thinnest quartile, 3.8, 2.4, then 1.3 cents in the
   deepest**. Polymarket publishes no
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

### The outcome audit: how we know the pairs are right

An earlier version of this backtest had six of 919 trades pay $0 or $2
instead of $1, meaning the two markets resolved inconsistently, which is
only possible if the pair was wrong. That prompted a full audit: for all
2,552 verified pairs, do the two markets' actual outcomes agree in the
way the pair's orientation says they must? This test uses no judgment
about titles or rules, only recorded outcomes, so it is independent of
the person who did the matching.

The first audit found 9 inconsistent pairs (0.35%). They were highly
systematic rather than random:

- **Seven were "both teams to score" markets.** Kalshi titles these
  generically ("Will both teams score?") and identifies the fixture only
  in its rules sentence and series ticker. The check meant to compare
  fixtures was counting any long word as evidence, so boilerplate like
  "score", "goals" and "match" satisfied it, and a Bundesliga fixture
  matched a Chinese Super League one.
- **One was a shared first name**: Austin Eckroat matched to Austin
  Smotherman, because the subject check accepted 50% token overlap.
- **One crossed sports entirely**: a generically titled "Will England
  win?" cricket market matched to the football World Cup Group L.

Each failure mode became a specific fix: parse the two team names out of
the Kalshi rules sentence and require both on the Polymarket side, require
the surname rather than half the tokens, and reject pairs whose texts name
different sports. A fourth fix was needed to make the strict name check
workable: accented characters were being turned into word breaks, so
"Mbappé" and "Mbappe" did not compare equal, which is why the loose rule
existed in the first place.

After the fixes, **zero of 2,507 non-basis-risk pairs are inconsistent**,
and **all 899 backtested trades pay exactly $1** at every slippage
assumption. For scale, two unrelated markets drawn at random from these
platforms would resolve inconsistently about 43% of the time, so a zero
rate across 2,507 pairs is strong evidence the matched set is clean.

The one pair that still resolves inconsistently is not an error, it is
the project's cleanest example of basis risk, and it is now labelled as
such: Polymarket asked whether Claude Fable 5 would be restored for US
customers by a date, while Kalshi asked whether a Source Agency would
REPORT that restoration. The event happened; the reporting condition did
not trigger. Same event, different resolution criteria, genuinely
different outcomes. That is basis risk realized rather than theorized,
and it is exactly why those pairs are excluded from the backtest.

Caveat on interpretation: consistent outcomes are necessary but not
sufficient for a correct pair, since two unrelated longshots both
resolving NO agree by luck. The honest reading is that this test cannot
prove precision is 100%, but it does place a hard upper bound on how many
pairs can be wrong in a way that would matter to the backtest.

## Phase 6: Does anything beat the market price?

Question: does a simple model with extra features predict resolution
better than the price alone? Setup: logistic regression on **logit(price)**
plus price momentum over the trailing 7 days, days of market lifetime,
category dummies, and platform. Using log-odds rather than raw price
matters: logistic regression is linear in log-odds, so a fitted
coefficient of exactly 1.0 with intercept 0 reproduces the market price
exactly. The coefficients therefore read directly as "how much does the
market need correcting". Temporal split: train on 17,953 markets
resolving through 2026-06-13, test on the 7,695 that resolved after.

### The answer is no, and the way we got there is the interesting part

| Model | Log loss | Brier |
|---|---|---|
| Market price alone | 0.3509 | 0.1136 |
| Recalibrated price (fitted slope and intercept) | 0.3508 | 0.1136 |
| Logistic regression with all features | 0.3512 | 0.1138 |
| Always predict the base rate (0.248) | 0.5607 | n/a |

The full model is very slightly WORSE than the raw market price: the
paired gain is -0.00027 with a t statistic of **-0.48**, and the features
add -0.00043 (t = -1.36) on top of recalibration. Recalibrating the price
alone adds 0.00016 (t = 0.42), also not significant, which independently
confirms the Phase 3 finding that these prices need no calibration
adjustment.

For scale, the market price cuts log loss from 0.561 (knowing only the
base rate) to 0.351. The price does essentially all of the work
available, and the extra features do not merely fail to help, they cost a
little by adding estimation noise.

### The lookahead bug that first said otherwise

The initial run of this model DID beat the market: log-loss gain 0.00338
with t = 5.30, apparently significant. Rather than reporting it, we asked
which single feature carried the gain. Ablating one feature group at a
time showed the answer was volume, alone, contributing 0.00306 of the
0.00338 (t = 6.14) while categories, momentum, and platform contributed
nothing.

That was the tell. The volume field in our schema is each market's
**lifetime** volume as recorded at ingestion, which is after the market
resolved. It is not knowable at the 24-hour snapshot. Markets that resolve
YES in dramatic fashion attract heavy late volume, so the model was
reading the future through a field that looked innocuous. Removing the
feature collapses the apparent edge entirely: on the current cleaned data
the model without it lands at t = -0.48, marginally worse than the raw
market price.

This is textbook lookahead bias, and it is worth stating plainly because
it is the exact failure mode that makes backtests look profitable when
they are not. The defense that caught it was not a code review; it was
insisting that any claimed edge be attributed to a specific feature, and
then asking whether that feature was truly knowable at decision time. A
point-in-time volume feature is possible in principle (cumulative volume
up to the snapshot, which Kalshi's candlesticks support and Polymarket's
price history does not) and is listed in FUTURE.md rather than bodged in.

### Honest caveats on the statistics

The paired t statistics above treat markets as independent. They are not:
multi-outcome events contribute several mechanically correlated legs, so
the true standard errors are wider than reported and the t statistics are
optimistic. This does not change the conclusion (a t of 0.08 is not
rescued by wider error bars) but it does mean the earlier t of 5.30 was
even less credible than it looked.

## Phase 7: Measured execution, and what it does to the arbitrage result

Every previous phase carried the same unverifiable assumption. Polymarket
publishes no historical order book, so the backtest applied a flat
slippage haircut to that leg and swept it from 0 to 3 probability points,
while noting in LIMITATIONS.md that a displayed price good for $50 is not
good for $5,000. Live capture replaces the assumption with a measurement.

`marketlens paper-trade` snapshots real depth on both venues and walks
each ladder for a target trade size, recording the volume-weighted price
actually achievable. It is read-only: no orders are placed and the
package holds no credentials.

### The measurement

Across 120 books captured from open markets:

| Platform | Avg cost above the touch at $50 | at $200 | at $1,000 |
|---|---|---|---|
| Polymarket | 3.01 points | **7.26 points** | 14.71 points |
| Kalshi | 0.02 points | 0.08 points | 0.66 points |

Kalshi's books are deep and tight. Polymarket's are not, which is
consistent with every other liquidity finding in this study. The number
that matters is the comparison: **the backtest assumed 1.0 point, and a
$200 Polymarket order really costs about 7.3.** The sensitivity sweep
stopped at 3 points, so it never reached the realistic range.

### Re-running the backtest at measured rather than assumed slippage

| Slippage | Source | Opportunities | Share of tradable pairs |
|---|---|---|---|
| 1.00 pt | original default | 906 | 42.9% |
| 3.01 pts | measured at $50 | 697 | 33.0% |
| 7.26 pts | measured at $200 | 474 | 22.4% |
| 14.71 pts | measured at $1,000 | 260 | 12.3% |

The opportunity set roughly halves at a $200 trade and falls by more than
two thirds at $1,000. Put beside the capacity result from the backtest
itself, where the median edge is 7.5 cents in the thinnest volume
quartile against 1.3 cents in the deepest, the two measurements agree:
the apparent edge sits precisely where the book cannot absorb a trade.

### The honest conclusion

The economic question this project set out to answer was whether
cross-platform disagreements were exploitable after costs. The answer is
no, and it is now supported by measurement rather than by a caveat. The
edge that survives fees does not survive execution, because it is
concentrated in exactly the markets whose displayed prices are least
representative of what you could actually trade.

That is a market-efficiency finding, and it is the result the spec
predicted would be the honest one.

### What paper trading adds, and why it has no signals yet

The harness also evaluates the Phase 5 entry rule against live books and
logs what it would have done, so that realised outcomes can later be
compared against predictions out of sample. It has recorded no signals
yet, and the reason is itself a finding: **the matched-pair opportunity
set is strongly seasonal.** A single World Cup produced 455 of the
study's 2,552 verified pairs. On a quiet day the two venues' near-dated
books share no propositions at all: Polymarket lists UFC fights and Dota
2 matches while Kalshi lists tennis sets and esports maps, and the best
fuzzy score between them is around 50, far below the acceptance
threshold. Signals will accumulate when the calendars overlap again.

This matters for interpreting Phase 4 and 5. Those results rest on a
window dominated by one tournament, so they describe cross-platform
behaviour during a period of unusually high overlap rather than a steady
state.


## Phase 8: Are the intervals honest? Correcting for dependence

Every confidence interval up to this point assumed markets were
independent observations. They are not. A "who wins the nomination"
event lists one binary leg per candidate and exactly one resolves YES,
so legs inside an event are mechanically correlated, and treating them
as independent makes intervals too narrow. This has been flagged in
LIMITATIONS.md since Phase 1; here it is measured.

The method is a cluster bootstrap: resample whole EVENTS with
replacement rather than individual markets, recompute the statistic, and
read the spread. It assumes nothing about the correlation structure
inside an event, which matters because a two-horse race and a
twenty-candidate field are differently dependent.

### How much dependence is there?

| Platform | Markets | Events | Legs per event | Design effect | Effective n |
|---|---|---|---|---|---|
| Polymarket | 14,658 | 11,022 | 1.3 | 1.24x | 9,500 |
| Kalshi | 10,661 | 6,119 | 1.7 | 1.41x | 5,378 |

So honest intervals are 24 to 41 percent wider than the ones reported in
Phase 3, and Kalshi's effective sample size is about half its raw market
count. That is a real correction, and it is the kind of thing that is
easy to leave unstated.

### Does anything change?

No conclusion is overturned.

- Kalshi longshot overpricing, the study's one significant bias, stays
  significant: implied 3.06 percent against a clustered interval of
  [1.82, 2.70] percent, which still excludes the implied price.
- Every result that was not significant, including both Polymarket tails
  and Kalshi favorites, remains not significant with wider intervals.
- The Phase 6 null result is if anything reinforced, since a t statistic
  of -0.48 does not become interesting when the error bars grow.

The honest summary is that the dependence correction matters for how
precisely the numbers should be quoted, not for what the study concludes.
Regenerate with `marketlens robustness`; full table in
`reports/robustness.md`.
