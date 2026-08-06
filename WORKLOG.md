# Worklog

## 2026-08-06: Live execution measurement and dependence correction

Two additions that close the project's two biggest open caveats.

**Live order book capture and paper trading** (read-only: no orders, no
credentials). The backtest could never see depth, so it assumed a flat
1-point Polymarket slippage haircut. Measured on 240 real books:
- mean cost above the touch is 3.0 points at \$50, 7.3 at \$200, 14.7 at
  \$1,000 on Polymarket, versus 0.02 to 0.66 on Kalshi
- but the distribution is the finding: the MEDIAN Polymarket market costs
  0.4 points at \$200, while the thinnest quartile costs 20.4 points
  (Spearman -0.55 against resting depth). Within-market variation is
  0.02 points, so this is a property of each book, not noise
- the backtest independently found the edge is 6x larger in the thinnest
  volume quartile, so the apparent arbitrage sits exactly where execution
  costs 20 points. That closes the economic question with two
  independent measurements
- paper signals need an open matched pair on both venues at once, and
  none exist today: the opportunity set is strongly seasonal, with one
  World Cup responsible for 455 of the 2,552 verified pairs

**Cluster bootstrap for contract dependence**, flagged since Phase 1 and
now quantified. Design effect 1.24x on Polymarket, 1.41x on Kalshi, so
honest intervals are 24 to 41 percent wider and Kalshi's effective sample
size is about half its market count. No conclusion changes: the one
significant bias (Kalshi longshot overpricing) survives clustering, and
every non-significant result stays non-significant.

Along the way: fixed a design error where the live sweep polled 12,000
Kalshi series individually (most of an hour) instead of using the
historical matches as a prior for which 179 series are worth watching.

## 2026-07-25: Case-study review exposes Kalshi stale prints, one finding retracted

Reviewing the case-study charts (spec calls them the most interview-useful
artifact) surfaced a 91 point one-day divergence that was too large to be
real. It was a Kalshi last-trade print of 0.96 in a market quoted 8 to 14
cents that day.

- Quantified: 2.2% of Kalshi rows with both a trade and a book have the
  trade more than 5 points outside the book, 0.12% more than 50 points.
  A related case is a trade at the ask of an empty 0.00/0.97 book.
- Fix: new analysis/prices.py with one shared usable_price rule (11 unit
  tests), replacing quote logic that had been duplicated in three modules.
  A Kalshi day needs a two-sided book tighter than 20 points; a trade is
  preferred only when consistent with the quotes.
- **Retraction:** the Phase 3 findings that Kalshi favorites were
  significantly overpriced and that its 0.6 to 0.9 range ran rich were
  artifacts. Both disappear on cleaned data. results.md now documents the
  retraction rather than quietly restating the numbers.
- What survives is cleaner: Kalshi longshots are significantly overpriced
  by 0.8pp (the classic favorite-longshot direction), and Kalshi's
  calibration error improves from 0.0004 to 0.0002 at 24h.
- Phase 6 conclusion strengthens: the feature model is now marginally
  WORSE than the raw price (t = -0.48).
- Case studies are now selected by phenomenon (fast-news blowout, single
  converging event, persistent offset, basis risk, typical tight
  tracking) rather than by volume, each annotated with what it shows.
  The old selection included a flat longshot that illustrated nothing.

## 2026-07-25: Outcome audit of the matched set

Sean asked for a 20-pair spot check. Did that, plus a stronger test that
needs no judgment: every verified pair predicts that its two markets
resolve consistently, and outcomes are recorded facts rather than my
reading of titles.

- First audit: 9 of 2,604 pairs inconsistent (0.35%), from exactly three
  causes: generic "both teams to score" titles matching across leagues
  (7), a shared first name (1), and a cricket market matched to football
  (1). Root cause of the biggest one was a fixture check that counted any
  long word, so boilerplate satisfied it.
- Fixes: parse both team names out of the Kalshi rules sentence, require
  the surname rather than 50% of tokens, reject cross-sport pairs, and
  normalize Unicode so accented names compare equal (that last one is
  what made the strict name check possible without losing real pairs).
- After fixes: 0 of 2,507 non-basis-risk pairs inconsistent, and all 899
  backtested trades pay exactly $1 at every slippage assumption. Verified
  set is now 2,552 pairs (was 2,604); 52 pairs removed.
- The one remaining inconsistent pair is the project's best basis-risk
  example and is now labelled as such: Fable 5 restored (Polymarket) vs
  a Source Agency REPORTING the restoration (Kalshi). Same event,
  different criteria, genuinely different outcomes.
- 20-pair random spot check (seed 2026): all 20 correct. Live re-fetch of
  5 Kalshi tickers matched stored outcomes for the 2 that had not yet
  been purged, which also re-confirms the rolling-purge finding.

## 2026-07-25: Phases 4 to 6 complete, all spec deliverables shipped

Done:
- Phase 4 divergence: 2,095 pairs, 50,276 pair-days, mean absolute
  spread 4.2 points, 3,641 divergence events with median half-life 1
  day, lead-lag showing Kalshi ahead by about a day (0.059 vs 0.000),
  5 case-study charts.
- Phase 5 backtest: entry rule with both taker fee schedules, Kalshi at
  closing bid/ask, Polymarket slippage swept 0 to 3 points. 919 of 2,144
  tradable pairs qualify at 1 point, opportunities falling 39% across
  the sweep. 913 of 919 trades paid exactly $1, and the 6 that did not
  are reported as an outcome-based precision estimate.
- Phase 6 prediction: nothing beats the price (t = 0.08). The first run
  DID at t = 5.30, entirely via a lifetime-volume feature that is only
  knowable after resolution. Caught by per-feature ablation, removed,
  documented as the phase's main lesson.
- Deliverables: README.md, INTERVIEW_PREP.md, FUTURE.md,
  marketlens run-all (verified end to end in 6.5 minutes offline),
  129 tests green, all 6 example SQL queries verified to execute.

Corrections made along the way:
- Polymarket seeds price history near 0.50 before a market's first trade
  and on no-trade days. This manufactured 47 cent fake arbitrages on
  golf longshots really priced at 0.3 cents. Cleaner plus a 25-point
  jump guard cut apparent opportunities from 65% of pairs to 43%.
- Two verified pairs were wrong (goals vs assists, SpaceX June vs
  full-year) and were caught by price data, not by text review.
- An unsupported claim in the Phase 3 write-up (that the backtest
  supported the "Kalshi YES is rich" reading) was checked and reversed:
  66% of trades buy Kalshi YES, which argues the other way.
- Regenerating data_quality.md had been silently dropping its
  hand-written notes; the notes now live in the generator.

Open for Sean:
- Spot-check roughly 20 random verified pairs in match_candidates.csv
  against the live market pages, since the matcher's author also did the
  verification. The 0.7% payout-mismatch rate is the current best
  independent estimate of that set's precision.

## 2026-07-10: Match verification pass (delegated to Claude by Sean)

- All 3,087 candidates at score 85+ verified against full descriptions
  and Kalshi rules text: class-level audits for template families plus
  individual reads for all 431 non-template pairs, then machine subject
  and fixture checks on every accepted pair.
- Result: 2,617 verified pairs in matches (orientation and basis_risk
  columns added), 469 rejected, 1 unresolved. 16 of 19 both-priced pairs
  usable. Codes and verified_by stamp written into
  reports/match_candidates.csv; engine in scripts/apply_verification.py.
- Independence caveat recorded in reports/matching.md; Sean asked to
  spot-check ~20 random verified rows as an audit when convenient.

## 2026-07-10: Phase 3, calibration analysis complete

Done:
- analysis/calibration.py: wilson_interval, brier_score,
  murphy_decomposition, calibration_table, price_at_horizon. All pure,
  15 unit tests with hand-computed toy cases.
- viz/plots.py: reliability diagrams with Wilson error bars and log-scale
  bin-count strips, validated palette.
- marketlens calibrate: snapshots at 7d and 24h before close
  (point-in-time, no lookahead), Kalshi no-trade candles use bid/ask mid
  only when spread <= 0.20. Writes reports/calibration_tables.md +
  4 figures. Narrative in reports/results.md (hand-authored, never
  overwritten by the tool).

Findings (details in results.md):
- Both platforms very well calibrated: 24h reliability 0.0001 (PM),
  0.0005 (Kalshi).
- Classic favorite-longshot bias mostly absent; mild significant longshot
  overpricing on Kalshi only (~0.7 points).
- Kalshi 0.6 to 0.9 buckets run 4 to 6 points rich (significant); genuine
  bias vs quote-handling artifact deliberately left open until Phase 5
  uses bid/ask separately.
- Clean sharpening 7d -> 24h on paired samples, both platforms.
- Thin-market miscalibration exists on Kalshi (4x reliability gap thin vs
  deep tercile) but not on Polymarket above its $1,000 floor.

## 2026-07-10: Phase 2, cross-platform matching built and run

Done:
- matcher.py: blocking (close-date window per bucket, coarse category
  buckets), token_set_ratio scoring, deterministic compatibility guards
  (numeric-token equality, max/min temperature, 1st/2nd half, toss,
  bare-moneyline rule, weather city from Kalshi series ticker), mutual-best
  filter. 13 new unit tests, each guard test reproduces a labeled false
  match from the tuning sample.
- Run on the overlap window (May to July 2026): 108,320 Polymarket vs
  235,642 Kalshi headline markets, 8,946 mutual-best candidates.
- Measured precision by hand-labeling stratified samples before and after
  guards (reports/match_precision_sample.csv): the guards moved the 85+
  bands from roughly 60% to roughly 90% precision. Details and the
  residual semantic false modes in reports/matching.md.
- Emitted reports/match_candidates.csv (8,946 rows, verified column empty)
  with verification instructions incl. leg orientation (inv) and basis
  risk (br) codes.

Waiting on Sean:
- Verification pass over match_candidates.csv, at minimum the 19
  both-priced pairs and the top of the 85+ band. Phase 4 uses only
  verified rows; Phase 3 (calibration) does not depend on matching and
  can start on go-ahead.

## 2026-07-10: Phase 1 sign-off decisions (Sean delegated, Claude chose)

- Kalshi window: accept the API-retained window (usable from May 2026).
  Cross-platform matching, divergence, and backtest therefore live in
  roughly May to July 2026. Kalshi calibration is reported as a
  short-window study beside Polymarket's 24 months, never pooled silently.
- Polymarket volume floor stays at $1,000; price sample stays at 15,000
  per platform. All three knobs are one-line config changes if revisited.
- Phase 4 option kept open: extend matched-pair price histories (not
  calibration) backward using Kalshi's S3 daily files, since outcomes for
  matched pairs come from the Polymarket leg.

## 2026-07-10: Phase 1 ingestion run complete

Numbers (full details and anomaly write-ups in reports/data_quality.md):
- Polymarket: 358,957 markets ingested, 344,556 headline (resolved binary,
  24h+ lifetime), coverage July 2024 to July 2026 with an upstream Gamma
  hole March 5 to 26, 2026 (verified live).
- Kalshi: 587,721 markets ingested, 235,702 headline, but usable coverage
  is effectively May 2026 onward: the API purges older settled markets and
  pre-May metadata has empty result fields. 337,584 resolved markets were
  excluded as sub-24h, validating Sean's inclusion rule.
- Prices: 15,000 markets sampled per platform (seed 42); 14,598 Polymarket
  histories (201,122 daily rows) and 14,977 Kalshi (105,759 rows, with
  historical bid/ask). A second upstream Polymarket hole: 402 sampled
  markets, mostly April 2026 and high volume, return empty price history
  from the CLOB endpoint (verified live).
- Storage: 3.6 GB SQLite plus 449 MB gzipped raw archive. Re-runs are
  idempotent and cache-backed (verified: zero network calls, zero row
  changes on identical re-run).
- Repo pushed to https://github.com/anytroops/market-lens (public), Sean's
  standing instruction: push every feature-sized commit immediately.
- YES base rate about 32% on both platforms (multi-outcome events make
  this expected); sports is 43% of Polymarket headline and 70% of Kalshi.

## 2026-07-09: Phase 1, ingestion pipeline built

Done:
- Project scaffolded: pyproject.toml, config.yaml (all assumptions live here),
  src/marketlens package per spec, typer CLI (marketlens init-db / ingest /
  quality-report), pytest suite for parsers, loaders, sampling, and stats
  helpers.
- SQLite schema: markets, prices, matches with spec primary keys and indexes,
  plus a headline_markets view that encodes the inclusion policy (resolved
  binary, lifetime 24h+) in one place.
- Shared BaseClient: per-request pacing, exponential backoff with jitter on
  429/5xx honoring Retry-After, descriptive user agent, and every raw response
  archived gzipped to data/raw/ before parsing. The archive doubles as a
  cache, so re-runs never re-hit the APIs. Verified: an identical re-run made
  zero network calls and duplicated zero rows.

Decisions made (with Sean's two calls as input):
- Inclusion policy implemented as agreed: markets alive under 24 hours are
  excluded from the headline dataset; window is 2024-07-09 to 2026-07-09.
- NEW, needs Sean's review: the raw universe is far larger than the spec
  assumed. Measured 2026-07-09: Kalshi has 60,000+ settled markets in a
  single day, Polymarket 6,000+, mostly 15-minute crypto, per-game sports
  props, and combo products. Pulling everything is not feasible or useful, so
  the frame is: (a) Polymarket metadata floor of $1,000 lifetime volume plus
  a server-side "started at least 1 day before scheduled end" prefilter;
  (b) Kalshi series-first ingestion skipping fifteen_min/hourly series and
  KXMVE/Exotics combo series; (c) price histories fetched for a seeded
  uniform random sample of 15,000 headline markets per platform rather than
  all of them (one API request per market is the binding cost). A uniform
  sample keeps calibration unbiased for the frame. All knobs in config.yaml.
- Kalshi API quirk discovered: status=settled silently omits markets settled
  before roughly Dec 2025. Fix: no status filter, resolve client-side from
  the result field. Correction noted in reports/phase0_recon.md.
- Polymarket keyset cursor parameter pinned down: after_cursor (from the
  API's own OpenAPI spec), page cap 100.

Major discovery, needs Sean's decision before Phase 3:
- Kalshi's trade API purges old settled markets. Direct GET returns 404 for
  anything settled before roughly Dec 2025; Dec 2025 to Apr 2026 is patchy;
  May 2026 onward looks complete. So the agreed 24-month window is NOT
  obtainable for Kalshi from the API, no matter how we ingest.
- Kalshi's public S3 daily reporting files (back to 2021) were evaluated as
  a fallback: they have daily high/low of last-trade prices but NO outcomes,
  NO titles. Verified concretely on FED-25MAR: finalized rows freeze at the
  last traded price, and never-traded strikes show 50. Inferring outcomes
  from final prices would bias calibration toward perfection, so it is
  ruled out for the calibration study.
- Options: (a) accept a shorter Kalshi window (API-retained period) for
  Kalshi calibration and matched-pair work, keeping Polymarket at 24 months;
  (b) later, use the S3 files to extend matched-pair PRICE histories for the
  divergence study only, where outcomes come from the Polymarket leg.
  Phase 1 proceeds with (a): the ingester scans the full window and stores
  whatever the API still has, and the data quality report shows the real
  coverage.

Open questions for Sean:
1. Is the $1,000 Polymarket volume floor acceptable for the frame, or would
   you rather lower it and accept a bigger, thinner dataset?
2. Is 15,000 sampled price histories per platform enough for Phase 3, or
   raise it (cost is roughly linear in requests)?
3. Kalshi history: OK to proceed with the API-retained window (roughly Dec
   2025 onward, complete from May 2026) as the Kalshi dataset, per the
   options above?

## 2026-07-09: Phase 0 complete, verdict GO

Done:
- Repo created at ~/Desktop/market-lens, spec copied in as SPEC.md.
- Live-verified both platforms: resolved-market listings and historical prices work with no auth on both. Details in reports/phase0_recon.md.
- Verified current fee schedules from documentation. Key correction to the spec: Polymarket now charges category-based taker fees (0.04 to 0.07 rate), it is no longer fee-free.

Decisions made:
- Kalshi backtest leg can use real historical bid/ask (candlesticks include yes_bid/yes_ask OHLC). Polymarket leg has no historical bid/ask, so it gets a configurable slippage haircut.

Open questions for Sean:
1. Inclusion policy for ultra-short markets (15-minute crypto up/down contracts dominate both platforms' recent volume). Exclude below a minimum lifetime, or treat as a separate stratum?
2. Target date window for ingestion (spec says 12+ months; more is cheap on both APIs).
3. Go-ahead to start Phase 1 (ingestion).
