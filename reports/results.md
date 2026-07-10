# Results

Narrative findings, maintained by hand as phases complete. All numbers
come from the generated tables in `calibration_tables.md` (rebuild with
`marketlens calibrate`); figures live in `figures/`.

## Phase 3: Calibration, in plain English

Setup: for every sampled resolved market we took its price 24 hours
before close (and separately 7 days before close), using only data
available at that moment, and asked how often markets priced at X%
actually happened. Polymarket sample: 14,189 markets at the 24h horizon.
Kalshi: 8,944. Wilson 95% intervals throughout.

### 1. Both platforms are strikingly well calibrated overall

The reliability component of the Brier score (average squared gap between
what markets said and what happened, bucket by bucket; 0 is perfect) is
0.0001 for Polymarket and 0.0005 for Kalshi at the 24h horizon. For
context, always answering 50% would score 0.25 on the full Brier scale.
The headline sentence for an interview: "Polymarket contracts priced
around 15 cents resolved YES 15.4% of the time, contracts priced around
97 cents resolved YES 98.1% of the time, and that diagonal pattern holds
across every bucket with tight confidence intervals" (see
`figures/calibration_polymarket_24h.png`).

### 2. The classic favorite-longshot bias is mostly absent, with one
mild exception

The textbook bias says longshots are overpriced and favorites underpriced.
At the 24h horizon:

- Polymarket longshots (mean implied 2.0%) resolved YES 1.7% of the time;
  the confidence interval [1.3%, 2.1%] contains the implied price. No
  significant bias.
- Polymarket favorites (implied 97.1%) resolved 98.1% [96.6%, 99.0%]:
  directionally the classic underpricing, not significant.
- Kalshi longshots (implied 3.1%) resolved 2.4% [2.0%, 3.0%]: the implied
  price sits just above the interval, a mild, marginally significant
  longshot overpricing worth about 0.7 probability points.
- Kalshi favorites (implied 96.8%) resolved 95.7% [93.6%, 97.1%]: if
  anything the OPPOSITE of the classic pattern, not significant.

The honest summary: at 24 hours out, on 2026 short-horizon markets, the
favorite-longshot bias is economically small where it exists at all. This
differs from the older literature, which mostly studied longer-horizon,
lower-liquidity markets.

### 3. Kalshi's mid-to-high range runs slightly rich

Kalshi buckets between roughly 0.6 and 0.9 sit consistently 4 to 6 points
below the diagonal, and significantly so: markets priced around 64 cents
resolved 59.4% (interval tops out at 63.9%), and markets priced around
75 cents resolved 69.4% (interval tops out at 74.0%). Two
candidate explanations, both recorded rather than resolved: a genuine
tendency of Kalshi buyers to overpay for likely-but-uncertain outcomes,
or a data artifact from our quote handling, since untraded Kalshi candles
contribute a bid/ask midpoint and stale one-sided books can bias mids
upward. Phase 5's execution-aware backtest, which uses bid and ask
separately, will speak to which explanation holds.

### 4. Markets sharpen as resolution approaches, cleanly

On the same set of markets scored at both horizons (so composition cannot
explain it): Polymarket's Brier improves from 0.1493 at 7 days to 0.1249
at 24 hours, with resolution (discrimination) rising 0.0603 to 0.0827.
Kalshi improves 0.0754 to 0.0561, resolution 0.1105 to 0.1291.
Information flows into prices as events near, exactly as theory predicts.

### 5. Thin markets are worse calibrated on Kalshi, not on Polymarket

Splitting each platform's 24h sample into volume terciles: Kalshi's thin
tercile has reliability 0.0033 vs 0.0009 for the deep tercile, about a
4x calibration-error gap supporting the "thin markets are worse
calibrated" hypothesis. Polymarket shows no such gradient (0.0010 thin vs
0.0009 deep), consistent with its $1,000 volume floor having already
removed the truly dead markets. Note the Brier itself RISES with volume
on both platforms; that is composition, not miscalibration: deep markets
are disproportionately sports games whose outcomes are genuinely close to
coin flips, so their irreducible uncertainty is higher.

### 6. Category cuts

Sports, the biggest slice on both platforms, is the best calibrated
(reliability 0.0001 Polymarket, 0.0007 Kalshi) despite the worst raw
Brier, again the composition effect. The worst calibration errors sit in
small-sample categories: Kalshi politics (0.0091, n=246) and
entertainment (0.0064, n=610). Mentions markets (Kalshi's "will X say Y"
products) have high Brier with decent calibration: hard events, honestly
priced.

### Caveats that travel with these numbers

- Kalshi's sample is May to July 2026 only (API retention); Polymarket
  spans 24 months. Cross-platform comparisons inherit that mismatch.
- Multi-outcome events contribute correlated legs, so the Wilson
  intervals, which assume independence, are somewhat too narrow.
- The samples are uniform random draws from each platform's headline
  frame, 15,000 per platform, of which the horizon subsets shown here are
  the markets alive long enough to have a price that early.
- Kalshi quote-handling choices (midpoint when spread at most 0.20) move
  its numbers slightly; the direction of finding 3 under trade-only
  prices is untested until Phase 5.
