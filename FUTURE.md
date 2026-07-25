# Future work

Deliberately out of scope for v1, recorded so the scope decision is
visible rather than implied. Ordered by expected value per unit of work.

## Directly unblocks an open question in the results

**Point-in-time volume.** Phase 6's only apparent "beat the market"
result came from a volume feature that turned out to be lifetime volume
known only after resolution (see results.md). A legitimate version needs
cumulative volume up to the snapshot moment. Kalshi's candlesticks carry
per-period volume so this is straightforward there; Polymarket's price
history does not, so it would need a different source or a
Kalshi-only model. Until then the honest answer stands: nothing simple
beats the price.

**Trade-only price series.** Kalshi days without trades currently
contribute a bid/ask midpoint, and that choice cannot be separated from
the finding that Kalshi's 0.6 to 0.9 buckets run rich. Rerunning
calibration on trades only, accepting the smaller sample, would settle
whether that is a real pricing bias or an artifact of quote handling.

**Intraday alignment for the divergence study.** Everything here is
daily, which forces every convergence half-life below one day to round
to exactly 1 and makes the lead-lag result (Kalshi appears to lead by
about a day) unresolvable at finer scale. Both APIs expose hourly or
minute fidelity; the cost is roughly 24x the storage and request volume
for the matched pairs.

**Execution depth.** The backtest's central caveat is that Polymarket
publishes no historical order book, so an apparent 3 cent edge may be
good for $50. Live order book snapshots collected going forward would
let a future version size trades instead of assuming a fill.

## Methodological upgrades

**Clustered standard errors.** Multi-outcome events contribute
mechanically correlated legs (exactly one candidate wins), so the Wilson
intervals and paired t statistics reported here are narrower than they
should be. Clustering by event id would widen them honestly. This does
not threaten any conclusion in the current results (the null findings
get more null, and the calibration effects are large relative to their
intervals) but it is the correct treatment.

**Semantic matching.** Fuzzy text matching plus deterministic guards
reached roughly 90% precision before human verification. A small local
sentence-embedding model might raise recall on paraphrased pairs like
"Will the Fed cut rates in September?" versus "Fed decreases rates at
Sept meeting?", which token overlap scores at only 54. Worth doing only
if measured against the existing labeled sample, not for decoration.

**Survivorship in the matched set.** Pairs enter the divergence study
only if both sides still had retrievable price history. Kalshi's rolling
purge removed 10% of verified pairs within a week of matching, and there
is no reason to assume the purged ones resemble the survivors.
Quantifying that would need a snapshot-based collection strategy running
forward in time.

## Explicitly not doing

**Deep learning, news scraping, or LLM features on the price series.**
The spec ruled these out for v1 and the Phase 6 result argues against
them: if a well-specified logistic regression cannot beat the market
price by a detectable margin, the bottleneck is not model capacity. A
larger model would mostly offer more ways to leak the future, which is
exactly the failure this project already caught once.

**Live trading of any kind.** This is an analysis of public data. No
orders, no wallets, no trading credentials.
