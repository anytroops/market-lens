# Interview Prep

Study document. Every number here comes from the project's own generated
reports. If an interviewer pushes past what is written, the honest answer
is "I would have to check the data", not an improvised number.

---

## 1. Walk me through the architecture end to end.

Two public REST APIs feed a shared HTTP client that handles rate
limiting, exponential backoff on 429s and 5xxs, and archives every raw
response gzipped to disk before anything parses it. That archive doubles
as a cache, so a full rerun of the pipeline is offline and costs zero API
requests, and a parsing bug never means re-downloading a day of data.
Parsed rows land in SQLite across three tables, markets, prices, and
matches, with upserts keyed on the primary key so ingestion is idempotent
and re-running never duplicates a row. On top of that sit four analysis
modules: calibration, cross-platform matching, divergence, and the
backtest, each built from small pure functions with hand-computed unit
tests, 129 of them. One command, `marketlens run-all`, regenerates every
table and figure in about six and a half minutes from cached data. The
design principle throughout was that the expensive, failure-prone part is
data collection, so it should happen once and everything downstream
should be cheap to redo.

## 2. What is a Brier score and what does its decomposition tell you?

A Brier score is just mean squared error for probability forecasts: take
the forecast minus the outcome coded as one or zero, square it, average.
Zero is perfect and 0.25 is what you get by always saying fifty percent.
The Murphy decomposition splits it into three pieces that answer
different questions. Reliability measures calibration error, how far each
probability bucket sits from the diagonal, and lower is better.
Resolution measures discrimination, how far your forecasts stray from the
base rate, and higher is better because a forecaster who always says the
base rate is perfectly calibrated but useless. Uncertainty is the base
rate variance, a property of the events rather than the forecaster. In my
data Polymarket at twenty-four hours out scores a Brier of 0.1258, of
which reliability is only 0.0001, so essentially all of the error is
irreducible event uncertainty rather than mispricing. That decomposition
is exactly why I can say the platforms are well calibrated but sports
markets still have high Brier scores: the games are genuinely close to
coin flips.

## 3. What is the favorite-longshot bias and did you find it?

The classic finding from racetrack betting is that longshots are
overpriced and heavy favorites are underpriced, so betting favorites
loses less than betting longshots. I tested both tails directly. On
Polymarket, contracts averaging 2.1 percent implied probability resolved
yes 1.8 percent of the time, with a Wilson interval of 1.4 to 2.1
percent, so the implied price sits inside the interval and there is no
significant bias. On Kalshi, contracts averaging 3.0 percent resolved 2.5
percent, interval 2.1 to 3.0, which is a mild overpricing of about half a
percentage point right at the edge of significance. The favorites side
was more interesting: Kalshi contracts averaging 96.7 percent resolved
only 94.9 percent, which is the opposite of the classic pattern and it is
significant. My honest conclusion is that the textbook bias has largely
been arbitraged out of modern liquid prediction markets, and the older
literature studied thinner, longer-horizon markets. I would rather report
an attenuated effect accurately than inflate it.

## 4. Why might two platforms price the same event differently?

Four reasons, and I can point to each in my data. First, different user
bases and capital: Polymarket is crypto-native and global, Kalshi is a
CFTC-regulated US venue, so they attract different traders with different
information and different costs of capital. Second, friction: moving
money between the two takes time, so a gap has to exceed the cost of
rebalancing before anyone bothers. Third, timing: my case study of the
2026 Spurs championship market shows the two venues tracking within a
mean 1.9 points across an entire regular season, then blowing out to a 37
point maximum spread during the playoffs, when prices move many times a
day and the same daily snapshot captures different moments. Fourth, and
most important for the analysis, resolution criteria genuinely differ
even when the titles match, which is basis risk. Across 2,095 matched
pairs the mean absolute spread was 4.2 points and it exceeded 5 points on
22 percent of pair-days, but the median divergence closed by half within
a single day.

## 5. Why doesn't the arbitrage survive fees? Walk me through the cost math.

Take a real trade from my data. On 13 May 2026, Polymarket priced "Will
Akshay Bhatia finish in the Top 10 at the 2026 PGA Championship?" at 16.5
cents, while Kalshi's equivalent contract showed a bid of 10 and an ask
of 11 cents. That is a 5.5 point disagreement, which looks like free
money. To lock in a dollar I buy the Kalshi yes at the ask, 11 cents, and
the Polymarket no at 83.5 cents, so gross cost is 94.5 cents for a
guaranteed dollar. Then reality: Polymarket has no historical order book,
so I charge a one point slippage haircut, taking that leg to 84.5 cents.
Both venues charge takers a fee of rate times price times one minus
price; Kalshi at 7 percent on an 11 cent contract is 0.69 cents, and
Polymarket's sports rate of 5 percent on an 84.5 cent contract is 0.65
cents. All in, 96.8 cents for a dollar, so the edge is 3.2 cents, not
5.5. Fees and slippage ate 42 percent of the gross gap, and this trade
was one of the survivors. Across the whole backtest, moving the slippage
assumption from zero to three points cuts the number of qualifying
opportunities by 39 percent, from 1,154 to 706.

## 6. What is lookahead bias and how did you avoid it?

Lookahead bias is using information in a backtest that would not actually
have been available at the moment of the decision, and it is the fastest
way to make a strategy look profitable when it is not. Structurally I
handled it by making every forecast a point-in-time snapshot, the last
observed price at or before the decision moment, and by never letting the
backtest enter on the resolution day itself. But the honest answer is
better than that, because I actually got caught. My Phase 6 model, which
tests whether extra features beat the market price, initially beat it
with a paired t statistic of 5.3, which looked publishable. Instead of
reporting it I ablated one feature group at a time and found that volume
alone contributed essentially the entire gain. The volume field in my
schema is lifetime volume recorded at ingestion, which is after
resolution, and markets that resolve yes dramatically attract heavy late
volume, so the model was reading the future through a field that looked
innocuous. Removing it collapsed the gain from a t of 5.3 to 0.08. The
lesson I took is that the defense is not code review, it is insisting
that any claimed edge be attributed to a specific feature and then asking
whether that feature was truly knowable at decision time.

## 7. What is basis risk in your matched pairs?

Basis risk is when two contracts describe what looks like the same event
but can actually resolve differently, so holding one long and one short
is not a riskless position. It shows up constantly in this data. My
favorite example is the Strait of Hormuz: Polymarket resolves "traffic
returns to normal" at the discretion of its integrity committee, while
Kalshi keys a specific number, the IMF PortWatch seven-day moving average
of transit calls. Same headline event, genuinely different triggers. I
flagged 56 pairs as basis risk during verification and excluded them from
the backtest entirely, because the strategy's guaranteed dollar payout
depends on exactly one leg paying. The check that it worked is empirical:
of 919 backtested trades, 913 paid precisely one dollar, and the six that
paid zero or two are residual verification errors, five of them soccer
markets where both venues used the same generic title for different
fixtures. That 0.7 percent error rate is an outcome-based precision
estimate for my matched set, which I trust more than any text-similarity
score.

## 8. What was the hardest engineering problem?

Cross-platform entity matching, and specifically the moment I realized
fuzzy text similarity alone was not going to work. The same event trades
under different titles, so I started with token-set similarity on
normalized titles, and precision in even the top score band was only
about 60 percent. The reason is a specific property of the metric: token
set ratio scores 100 whenever one title's tokens are a subset of the
other's, so "Brazil: 5+ corners" matched "Brazil vs Norway: O/U 6.5 Total
Corners" perfectly. What saved it was that the failures were systematic
rather than random, so each became a deterministic rejection rule:
numeric tokens must match exactly, highest never matches lowest, first
half never matches second half, a bare "A vs B" moneyline only matches
propositions about winning, and weather pairs must agree on a city that
Kalshi encodes in the series ticker rather than the title. That lifted
measured precision to about 90 percent, after which I checked candidates
against both platforms' full resolution rules text. The close second was
building point-in-time correct price alignment, which is where I found
that Polymarket seeds price history with a placeholder near 50 cents
before a market's first trade, an artifact that was manufacturing 47 cent
fake arbitrages on golf longshots actually priced at a third of a cent.

## 9. What would you build next with more time?

Three things, in order. First, a point-in-time volume feature, because
that is the one thing that would let me redo the Phase 6 experiment
legitimately after the lookahead problem killed the first attempt;
Kalshi's candlesticks carry per-period volume so it is feasible there.
Second, intraday alignment for the divergence study, since everything I
have is daily, which forces every convergence faster than a day to round
to exactly one and makes my lead-lag result unresolvable at finer scale.
Third, live order book collection going forward, because the single
biggest weakness of the backtest is that Polymarket publishes no
historical depth, so I cannot distinguish a real three cent edge from one
that exists for fifty dollars of size. I deliberately did not add deep
learning or news features, and I would push back on doing so, because if
a well-specified logistic regression cannot beat the market price by a
detectable margin then the bottleneck is not model capacity, it is that
the price is already efficient. A bigger model would mostly offer more
ways to leak the future.

## 10. What is the biggest limitation of your results?

The Kalshi coverage window, without question. Their trade API purges
older settled markets, so despite ingesting a 24-month window my Kalshi
data effectively begins in May 2026, roughly ten weeks, against 24 months
for Polymarket. That means every cross-platform result, the divergence
study and the entire backtest, lives in a narrow and unusual window
dominated by one World Cup and one set of playoffs, and I cannot claim it
generalizes across market regimes. I checked whether the public S3
reporting files could extend it and they cannot for calibration purposes,
because they contain prices but no outcomes, and inferring outcomes from
final prices would make calibration look artificially perfect by
construction. A close second limitation is statistical dependence:
multi-outcome events contribute mechanically correlated legs, so my
Wilson intervals and t statistics are narrower than they should be. That
does not threaten the null results, since wider error bars only make a t
of 0.08 more null, but it does mean my significant findings deserve more
caution than the raw numbers suggest.

---

## Numbers worth memorizing

| Fact | Number |
|---|---|
| Markets ingested | 358,957 Polymarket + 587,721 Kalshi |
| Headline resolved set | 344,556 + 235,702 |
| Verified matched pairs | 2,604 |
| Tests | 129 passing |
| Calibration error (reliability), 24h | 0.0001 PM, 0.0004 Kalshi |
| Brier, 24h | 0.1258 PM, 0.1140 Kalshi |
| Longshot bias | 0.3pp PM (ns), 0.5pp Kalshi |
| Sharpening, paired 7d to 24h | PM Brier 0.1344 to 0.1145 |
| Mean absolute spread | 4.2 points over 50,276 pair-days |
| Divergence events, median half-life | 3,641 events, 1 day |
| Backtest at 1pt slippage | 919 of 2,144 pairs, median edge 3.2c |
| Slippage sensitivity | 1,154 opportunities at 0pt, 706 at 3pt |
| Trades paying exactly $1 | 913 of 919 |
| Features beating the price | none, t = 0.08 |
