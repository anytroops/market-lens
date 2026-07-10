# Cross-Platform Contract Matching: Method and Measured Accuracy

Phase 2 deliverable. Generated candidates live in the `matches` table and
`reports/match_candidates.csv` (8,946 rows). Nothing is used downstream
until human-verified.

## The problem

The same real-world event trades under different names on the two
platforms. Comparing all 108,320 Polymarket markets in the overlap window
(May to July 2026, set by Kalshi's retention) against all 235,642 Kalshi
markets would be 25 billion comparisons, nearly all meaningless. Matching
runs in four stages:

1. **Blocking.** Only compare markets whose close dates are within a window
   (1 day for daily sports and weather, 3 days otherwise) and whose
   categories map to the same coarse bucket (sports, politics, econ,
   crypto, entertainment, weather, mentions, science). This cuts the
   comparison space by about four orders of magnitude.
2. **Fuzzy scoring.** rapidfuzz `token_set_ratio` on normalized titles
   (lowercased, punctuation stripped, digits and thresholds preserved).
   Kalshi multi-candidate markets repeat the event question in the title
   and put the actual proposition in `yes_sub_title`, so the Kalshi match
   text concatenates both.
3. **Deterministic compatibility guards.** A first hand-labeled sample of
   105 pairs showed raw fuzzy scores are not enough: `token_set_ratio`
   scores 100 whenever one title's tokens are a subset of the other's, so
   "Brazil: 5+ corners" matched "Brazil vs Norway: O/U 6.5 Total Corners"
   perfectly. Precision in the TOP score band was only about 60%. The
   false matches were systematic, so each mode became a deterministic
   rejection rule:
   - numeric tokens must agree exactly (kills 15.5 vs 15+, 99-100 vs
     100-101, May 16 vs May 19); 4-digit years are ignored
   - "highest/maximum" never matches "lowest/minimum" (temperature markets)
   - "1st half" never matches "2nd half"
   - toss markets only match toss markets
   - a bare "A vs B" title (a moneyline) only matches texts about winning
   - weather pairs must agree on city, which on Kalshi lives in the series
     ticker (KXHIGHNY means New York), not the title
4. **Mutual best.** A pair survives only if each side is the other's best
   surviving candidate, which makes the mapping one-to-one. Precision over
   recall throughout: a false pair poisons the divergence and arbitrage
   studies, a missed pair just shrinks the sample.

## Measured accuracy

Stratified random samples hand-labeled by reading both titles (labels in
`reports/match_precision_sample.csv`, reproducible with seed 23):

| Score band | Precision before guards | Precision after guards |
|---|---|---|
| 95 to 100 | ~60% (9/15) | 87% (13/15) |
| 85 to 95  | ~54% (7/13) | 93% (14/15) |
| 75 to 85  | ~58% (7/12) | 73% (11/15) |
| 60 to 75  | ~13% (4/30) | 40% (6/15) |

Candidate counts after guards: 1,934 pairs at 95+, another 1,143 at 85 to
95, 1,562 at 75 to 85. Recommended acceptance set for verification:
**score 85 and above (3,077 pairs, expected ~90% precision before human
review)**. The 75 to 85 band can be mined later if more pairs are needed.

## What still gets past the guards (why humans verify)

The residual false modes are semantic, not lexical:

- proposition scope: "Will Ole Miss WIN the College World Series?" vs
  "Will Ole Miss vs Oklahoma BE THE MATCHUP?"
- prize structure: "Will Latvia win Eurovision?" vs "Will Latvia win the
  JURY VOTE?" (the jury vote is one component of winning Eurovision)
- superlatives over different metrics: "most assists" vs "most goals"
- set semantics: "a team from England wins" vs "Arsenal wins"
- interval semantics: "between 94 and 95 degrees" vs "95 or above"
- near-identical names: Ali Ahmed vs Ali Iyad Olwan (different players)

## Instructions for verification (match_candidates.csv)

Fill the `verified` column with:
- `1`: same proposition, same orientation
- `inv`: same proposition, opposite orientation. Example: the Polymarket
  market is "Set 1 Winner: Bonzi vs Zverev" (its stored price tracks the
  FIRST listed outcome, Bonzi) while Kalshi asks "Will Zverev win set 1?".
  The pair is valid but one series must be flipped to 1 - p.
- `0`: different propositions.
- `br`: same event but resolution criteria differ enough to matter
  (different data source, deadline, or edge-case rules). These pairs are
  usable for divergence but NOT for the arbitrage backtest.

Basis risk, in one sentence: if the two contracts can resolve differently
despite describing the same event, price divergence between them is not
free money, it is compensation for that residual difference. Live examples
from this dataset: Polymarket resolves Strait of Hormuz shipping "returns
to normal" editorially, while Kalshi keys the IMF PortWatch 7-day moving
average of transit calls; a California "advance from the primary" market
(top-2) is not a "finish 1st in the primary" market.

Suggested verification order: the 19 pairs where both sides already have
sampled price histories (`both_have_prices = 1`), then score 85+ sorted by
volume. Price histories for verified pairs that lack them are fetched on
demand in Phase 4 (ingestion is resumable by design).

## Honest limitations

- My own labels tuned the guards AND estimated the precision above, so the
  85+ precision estimate has optimism risk; Sean's verification pass is
  the real gate for anything used downstream.
- Mutual-best filtering costs recall when one platform lists the same
  proposition twice (only one copy can win) and when the true counterpart
  is missing (the second-best impostor can win instead; the guards exist
  to catch exactly this case).
- Esports titles conflate "map N winner" and "match winner" easily; the
  numeric guard catches map-number mismatches but not map-vs-match.
- The overlap window is May to July 2026 (Kalshi retention limit), so
  matched pairs skew heavily toward sports (85% of candidates).
