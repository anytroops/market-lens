# Limitations

Honest caveats, maintained continuously. Each entry says what the limitation
is, why it exists, and what it affects.

## Data frame and sampling (Phase 1)

- **The dataset is a defined frame, not "all markets."** Phase 0 follow-up
  measurement (2026-07-09) found tens of millions of closed markets in the
  24-month window across both platforms, dominated by 15-minute crypto
  contracts, per-game sports props, and multivariate combo products. The
  ingested frame is: resolved binary markets, lifetime of 24 hours or more
  (Sean's decision), scheduled close in the window, Polymarket volume of
  $1,000 or more, and Kalshi series excluding fifteen_min/hourly frequencies
  and KXMVE/Exotics combo series. Calibration conclusions apply to this
  frame, not to the excluded short-cycle stratum.
- **Price histories are sampled.** Fetching prices costs one API request per
  market, so daily histories cover a seeded uniform random sample (15,000 per
  platform) of the frame rather than every market. Uniform sampling keeps
  calibration estimates unbiased for the frame; it does add sampling noise,
  which per-bucket confidence intervals in Phase 3 will reflect.
- **The Polymarket volume floor selects on liquidity.** Markets under $1,000
  volume are absent, so "thin market" findings only speak to thin-but-not-dead
  markets. Kalshi has no volume floor in the frame.

## Statistical dependence

- **Multi-outcome events create dependent rows.** A "who wins the
  nomination" event with 8 candidates contributes 8 binary legs whose
  outcomes are mechanically correlated (exactly one resolves YES). Error
  bars that treat legs as i.i.d. are too narrow. Event ids (Polymarket) and
  event tickers (Kalshi) are retained in raw_json so Phase 3 can cluster or
  deduplicate.
- **Sports and politics markets cluster in time and topic** (same game, same
  election), a second source of dependence beyond shared events.

## Execution realism

- **Polymarket has no historical bid/ask.** The prices-history endpoint
  returns one price series only. The backtest applies a configurable slippage
  haircut on the Polymarket leg instead of real spreads. Kalshi candlesticks
  do include historical yes_bid/yes_ask, so that leg is execution-realistic.
- **Displayed prices are not depth.** A price good for $50 is not good for
  $5,000. The backtest will carry a minimum-size caveat rather than model
  book depth, which is not available historically.

## Field semantics

- **Polymarket resolve_ts is approximated by closedTime.** Gamma exposes no
  separate resolution timestamp; on Polymarket trading stops at resolution,
  so the approximation is close, but disputes can add lag.
- **Volume units differ across platforms.** Polymarket volume is USD;
  Kalshi volume is number of contracts. Cross-platform volume comparisons
  are therefore ordinal at best; liquidity terciles are computed within
  platform only.
- **Windowing is on scheduled end date (Polymarket).** The frame keys on
  endDate server-side; a market resolved early whose scheduled end falls
  outside the window is not in the frame even though it resolved inside it.
- **Category taxonomies differ.** Kalshi has a clean category field per
  series; Polymarket categories come from tags (newer markets) or a legacy
  category field. Phase 3 category cuts will need a small manual mapping to
  a common taxonomy.
