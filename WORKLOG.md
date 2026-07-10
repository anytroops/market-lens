# Worklog

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
