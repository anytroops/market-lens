# Phase 0 Recon: API Accessibility Audit

Date: 2026-07-09
Method: live unauthenticated HTTP calls from this machine, plus fee documentation lookup. All endpoints below were verified working today unless noted.

## Verdict: GO

Both platforms expose resolved-market metadata and historical prices with no account and no API key. Data volume is far above the 5,000-contract target. One spec assumption was overturned: Polymarket now charges taker fees (see Fees below), which the backtest cost model must include.

## Polymarket

| Check | Result |
|---|---|
| List resolved markets | WORKS. `GET https://gamma-api.polymarket.com/markets?closed=true&limit=...` returns question, description, category, endDate, closedTime, outcomes, outcomePrices, volume, liquidity, clobTokenIds. No auth. |
| Deep pagination | Plain `offset` is capped (validation error well below 5,000). The API's own error message points to `GET /markets/keyset` for deep pagination, verified working. Note: the `id_gt` param I guessed appears to be ignored, so the exact cursor parameter name must be pinned down from the response schema in Phase 1. Date-window pagination (`end_date_min` / `end_date_max`) also works as a fallback. |
| Price history | WORKS. `GET https://clob.polymarket.com/prices-history?market=<clobTokenId>&interval=max&fidelity=1440` returns timestamped prices in 0 to 1 units. `fidelity` is in minutes (1440 = daily, 60 = hourly). No auth. |
| Bid/ask history | NOT directly available historically. `prices-history` returns a single price series (midpoint/last). Live books exist via CLOB but that does not help a backtest. Consequence: the backtest must apply a configurable slippage haircut on the Polymarket leg (spec already anticipates this). |
| History depth | Markets back to 2020 confirmed (market id 12 is from Oct 2020, and its full daily price history is retrievable). |
| Scale | Max market id observed today: 2,865,801. IDs are sparse but the closed-market universe is clearly in the hundreds of thousands. |

## Kalshi

| Check | Result |
|---|---|
| List settled markets | WORKS, no auth. `GET https://api.elections.kalshi.com/trade-api/v2/markets?status=settled&limit=1000` returns ticker, event_ticker, title, close/expiration/settlement times, `result` (yes/no), volume, liquidity, and current bid/ask fields. Cursor-based pagination confirmed working at limit=1000 per page. `min_close_ts` filter works for windowing. |
| Price history | WORKS, no auth. `GET /trade-api/v2/series/{series_ticker}/markets/{ticker}/candlesticks?start_ts=...&end_ts=...&period_interval=...` (period in minutes: 1, 60, 1440). Returns OHLC price AND separate `yes_bid` / `yes_ask` OHLC per candle, plus volume and open interest. |
| Bid/ask history | AVAILABLE historically via candlesticks. This is better than expected and directly supports execution-realistic backtesting on the Kalshi leg. |
| Auth | None needed for any read endpoint tested. No account required. |
| Units | Prices returned in dollar strings (e.g. "0.5800"), i.e. already 0 to 1 probability units, not the 1 to 99 cents integers the spec expected. Minor schema note for ingestion. |

## Fees (verified from documentation, retrieved 2026-07-09)

The spec's assumption that Polymarket is fee-free is outdated. Both platforms now use the same functional form, taker-only:

fee = feeRate x C x P x (1 - P), where C = contracts and P = price in dollars.

| Platform | Fee rate | Source |
|---|---|---|
| Kalshi | 0.07 on standard markets, rounded up; makers pay 25% of taker fee; premium categories (e.g. crypto) can be higher. Verify per-series `fee_multiplier` fields during ingestion. | kalshi.com/docs/kalshi-fee-schedule.pdf (July 2026 update), help.kalshi.com |
| Polymarket | Category-based taker rates: crypto 0.07, sports 0.05, finance/politics/mentions/tech 0.04, econ/culture/weather/other 0.05, geopolitics 0. Makers never pay. | docs.polymarket.com/polymarket-learn/trading/fees |

Both formulas go into `config.yaml` with these source links and today's retrieval date.

## Data-design findings that affect later phases

1. Both platforms are flooded with ultra-short crypto up/down markets (15-minute Doge/ETH/XRP contracts, multivariate esports combos). These would dominate any naive "all resolved markets" pull and distort the calibration study toward one weird market type. Phase 1 needs an explicit inclusion policy (e.g. minimum lifetime of 24 hours, or analyze short-cycle markets as a separate stratum). Flagging now per the working agreement, decision is Sean's.
2. Kalshi settled-market metadata includes `rules_primary` / `rules_secondary` text fields. Useful later for the basis-risk check on matched pairs.
3. Polymarket multi-outcome events arrive as separate binary markets grouped under an `events` array, matching the spec's plan to treat each binary leg as a row.

## Corrections found during Phase 1 (2026-07-09)

1. The Kalshi row above says `status=settled` listing works. It does return
   markets, but it silently omits everything settled before roughly December
   2025 (older markets report status `closed` or `finalized`, and the
   endpoint rejects those as filter values). Phase 1 queries with no status
   filter and keeps markets whose `result` field is `yes` or `no`.
2. Worse: Kalshi's trade API has a retention cliff. Markets settled before
   about December 2025 are purged entirely (404 on direct GET, absent from
   every listing route including nested event markets), and December 2025 to
   April 2026 coverage is patchy. The recon table's "history depth" optimism
   was wrong for Kalshi: 24 months of Kalshi resolved markets are NOT
   obtainable from the API. The public S3 daily reporting files go back to
   2021 but contain last-trade prices only (no results, no titles), so they
   cannot support calibration. Consequence and options are written up in
   WORKLOG.md and LIMITATIONS.md; Kalshi calibration is limited to the
   API-retained window.

## Rate limits observed

None hit during recon (single sequential requests). Kalshi documents rate limits on its API; the shared client should default to modest concurrency, exponential backoff on 429/5xx, and disk caching regardless.
