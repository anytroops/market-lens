# Worklog

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
