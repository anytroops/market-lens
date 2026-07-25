# market-lens

**Do prediction markets know what they are talking about, and can you arbitrage the disagreements between them?**

An end-to-end data pipeline and statistical study of roughly 580,000 resolved
binary contracts from Polymarket and Kalshi. It audits how well market prices
work as probability forecasts, matches equivalent contracts across the two
venues, measures how far their prices diverge and how fast the gaps close, and
backtests a fee-adjusted arbitrage strategy to see whether the divergences were
ever exploitable after costs.

Analysis of public data only. No orders were placed, no trading credentials
exist in this project.

## Headline findings

**1. Both platforms are remarkably well calibrated.** When a contract is priced
at 15 cents 24 hours before it closes, it resolves YES about 15% of the time.
The calibration error component of the Brier score is 0.0001 for Polymarket
(n = 14,638) and 0.0004 for Kalshi (n = 11,010), against 0.25 for a forecaster
who always says 50%.

![Polymarket calibration](reports/figures/calibration_polymarket_24h.png)

**2. The textbook favorite-longshot bias has nearly vanished.** Classic studies
find longshots badly overpriced. Here, Polymarket contracts averaging 2.1%
implied probability resolved YES 1.8% of the time (95% CI [1.4%, 2.1%], not
significant), and Kalshi's averaging 3.0% resolved 2.5% ([2.1%, 3.0%], barely
significant). The bias survives at 0.3 to 0.5 percentage points, an order of
magnitude smaller than the older literature on thinner markets.

**3. Markets sharpen as resolution approaches.** On identical market sets scored
at both horizons, so composition cannot explain it, Polymarket's Brier score
improves from 0.1344 at 7 days out to 0.1145 at 24 hours, and Kalshi's from
0.0766 to 0.0582. Resolution (discrimination) rises in step.

**4. The two venues disagree constantly, but briefly.** Across 2,095 verified
matched pairs and 50,276 pair-days, the mean absolute spread is 4.2 probability
points, exceeding 5 points on 22% of days and 10 points on 10%. Of 3,641
divergence events, the median half-life is **1 day**: gaps open and close fast.

![Spread distribution](reports/figures/spread_distribution.png)

**5. Apparent arbitrage survives fees on paper, but not scrutiny.** At a
1-point slippage assumption, 919 of 2,144 tradable pairs (43%) showed a
fee-adjusted combined cost below \$1, median edge 3.2 cents and median 76%
annualized. Raising the slippage assumption to 3 points cuts that to 33% of
pairs. The honest reading is in [LIMITATIONS.md](LIMITATIONS.md): the edge
concentrates in thin, early-life quotes where the displayed price is good for
tens of dollars, not thousands, and Polymarket has no historical order book to
verify depth against. This is a market-microstructure finding, not a trading
strategy.

Full write-up with all numbers: [reports/results.md](reports/results.md).

## Architecture

```
   Polymarket Gamma API            Kalshi trade-api v2
   (metadata, keyset paging)       (series, markets, candlesticks)
            |                                |
            +--------------+-----------------+
                           |
                  ingest/base.py
       rate limiting, exponential backoff, gzip raw archive
       (data/raw/ doubles as a cache: re-runs never re-hit the API)
                           |
                  SQLite (data/marketlens.sqlite)
         markets | prices | matches | headline_markets view
                           |
        +------------------+------------------+---------------+
        |                  |                  |               |
   calibration.py     matching/          divergence.py    backtest.py
   Wilson CIs         blocking +         daily align,     entry rule,
   Brier + Murphy     token_set_ratio    spread stats,    fees, slippage,
   decomposition      + guards +         half-life        hold to resolution
                      mutual best
        |                  |                  |               |
        +------------------+------------------+---------------+
                           |
                  reports/ (tables, figures, CSVs)
```

Every statistic is a small pure function with a hand-computed unit test.
**111 tests, all passing.**

## Key engineering problems

**Cross-platform entity matching.** The same event trades as "Will the Fed cut
rates in September?" on one venue and "Fed decreases rates at Sept meeting?" on
the other. Fuzzy text similarity alone gave roughly 60% precision even in the
top score band, because `token_set_ratio` scores 100 whenever one title's tokens
are a subset of the other's ("Brazil: 5+ corners" vs "Brazil vs Norway: O/U 6.5
Total Corners"). The failure modes were systematic, so each became a
deterministic rejection rule: numeric tokens must match exactly, max never
matches min, 1st half never matches 2nd half, a bare "A vs B" moneyline only
matches propositions about winning, weather pairs must agree on a city that
Kalshi encodes in the series ticker rather than the title. That lifted measured
precision to roughly 90%, after which every candidate was checked against both
platforms' full resolution rules text. Method and measured accuracy:
[reports/matching.md](reports/matching.md).

**Point-in-time discipline.** Every forecast is the last price at or before the
snapshot moment, and the backtest can only enter on data available that day.
Lookahead bias is the fastest way to fake a profitable strategy.

**Silent data artifacts.** Polymarket's price endpoint emits a placeholder near
0.50 before a market's first trade and on no-trade days. Left alone, it
manufactured 47 cent "arbitrage" on golf longshots that were really priced at
0.3 cents on both venues. Detecting and stripping those, plus a guard against
entering on any single-day price jump above 25 points, cut the apparent
opportunity rate from 65% of pairs to 43%.

## Reproducing

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

```bash
.venv/bin/marketlens ingest --platform all --since 2024-07-09
```

```bash
.venv/bin/marketlens match --threshold 60 && .venv/bin/marketlens fetch-pair-prices
```

```bash
.venv/bin/marketlens calibrate && .venv/bin/marketlens diverge && .venv/bin/marketlens backtest
```

```bash
.venv/bin/python -m pytest
```

All assumptions (date window, inclusion policy, fee schedules with source links
and retrieval dates, slippage) live in [config.yaml](config.yaml), not in code.
Raw API responses are archived before parsing, so re-runs are free and parsing
bugs never require re-downloading.

## Stack

Python 3.11+, httpx, pandas, numpy, scipy, rapidfuzz, pydantic, typer,
matplotlib, pytest, SQLite. Analytical SQL (joins, window functions, NTILE
terciles) in [sql/example_queries.sql](sql/example_queries.sql).

## Repo map

| Path | What |
|---|---|
| `src/marketlens/ingest/` | API clients, shared retry/cache layer |
| `src/marketlens/db/` | Schema, idempotent upsert loaders |
| `src/marketlens/matching/` | Blocking, fuzzy scoring, compatibility guards |
| `src/marketlens/analysis/` | Calibration, divergence, backtest |
| `reports/` | Findings, generated tables, figures, verification CSVs |
| `LIMITATIONS.md` | Every caveat found, maintained continuously |
| `WORKLOG.md` | Decision log |
