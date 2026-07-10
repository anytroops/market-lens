# Project Spec: Prediction Market Calibration & Cross-Platform Divergence Engine

**Working name:** `market-lens` (rename freely)
**Owner:** Sean Xue
**Purpose of this document:** This is the master spec for Claude Code. Read this entire file before writing any code. Follow the phases in order. Do not skip Phase 0.

---

## 0. Context and Goals (read carefully, this shapes every decision)

### What this project is
An end-to-end data pipeline and statistical analysis engine that:
1. Ingests thousands of resolved prediction-market contracts from Polymarket and Kalshi via their public APIs.
2. Audits market calibration (when the market says 70%, does the event happen 70% of the time?), including Brier score decomposition and favorite-longshot bias analysis.
3. Matches equivalent contracts across the two platforms, quantifies price divergence between them, and measures how fast divergences converge.
4. Backtests a fee-adjusted cross-platform arbitrage strategy to test whether observed divergences are actually exploitable after transaction costs.
5. (Stretch) Tests whether simple features add any predictive information beyond the market price itself.

### What this project is NOT
- NOT a trading bot. No orders are ever placed. No wallets, no API keys with trading permissions, no real money. Analysis of public data only.
- NOT a claim that we "beat the market." The honest expected headline is "markets are mostly well calibrated, longshot bias exists, and cross-venue arbitrage mostly does not survive fees." Negative results are results. Rigor over hype.

### Why this project exists (motivational context for framing decisions)
This is a resume project for quantitative analyst and SWE recruiting. Every architectural and analytical choice should optimize for two things:
1. **Defensibility in interviews.** Sean must be able to explain every component. Prefer simple, explainable methods over clever, opaque ones. A logistic regression Sean can defend beats a transformer he cannot.
2. **Rigor vocabulary.** The final results must legitimately support statements like: "temporal out-of-sample evaluation," "Brier score decomposition into reliability and resolution," "fee-adjusted backtest," "convergence half-life."

### Teaching mode (important, always on)
Sean is learning this domain as he builds. For every phase and every non-obvious decision:
- Explain WHAT you are building and WHY in plain language before writing the code.
- After each phase, produce a short plain-English summary of what was learned from the data.
- When introducing a statistical concept (Brier score, calibration, half-life, log-loss), define it in one or two sentences with an intuitive example before using it.
- Never dump a wall of code without a preceding explanation Sean could repeat in an interview.

### Hard style rule
Never use em dashes in any generated text, comments, docstrings, README content, or commit messages. Use commas, colons, periods, or parentheses instead. No exceptions.

---

## 1. Tech Stack and Engineering Standards

- **Language:** Python 3.11+
- **Core libraries:** `httpx` (API calls), `pandas`, `numpy`, `scipy`, `scikit-learn`, `matplotlib` (plots), `rapidfuzz` (fuzzy string matching), `pydantic` (schemas), `typer` (CLI), `pytest`
- **Storage:** SQLite for raw and cleaned data (single file, zero setup, and it lets the resume honestly say SQL). Parquet acceptable for large price-history tables. Include a small set of analytical SQL queries (joins, aggregations, window functions) as first-class artifacts in `sql/`, not just ORM calls, so the SQL skill claim is real.
- **Repo structure:**

```
market-lens/
  README.md
  SPEC.md                  <- this file
  LIMITATIONS.md           <- honest caveats, maintained continuously
  pyproject.toml
  config.yaml              <- API endpoints, date ranges, fee assumptions
  src/marketlens/
    ingest/
      polymarket.py
      kalshi.py
      base.py              <- shared client: retries, rate limiting, caching
    db/
      schema.py            <- table definitions
      loaders.py
    matching/
      matcher.py           <- cross-platform contract matching
    analysis/
      calibration.py
      divergence.py
      backtest.py
      prediction.py        <- Tier 3 lite
    viz/
      plots.py
    cli.py
  sql/
    example_queries.sql
  tests/
  notebooks/               <- exploratory only, all real logic lives in src/
  reports/
    figures/
    results.md
```

- **Standards:** type hints everywhere, docstrings on public functions, small pure functions for all statistics (unit-testable), config-driven (no magic constants inline), deterministic runs (set seeds), raw API responses cached to disk so re-runs never re-hit APIs unnecessarily.
- **Tests:** every statistical function gets a unit test with a hand-computable toy case (e.g., Brier score of a known small vector). Matching logic gets fixture-based tests. Target: the stats core is fully tested even if API clients are lightly tested.
- **Git:** commit at the end of each phase minimum, descriptive messages, no giant monolithic commits.
- **Rate limiting and etiquette:** respect API rate limits, exponential backoff on 429/5xx, cache aggressively, identify with a normal user agent. This is read-only public data collection, keep it polite.

---

## 2. Phase 0: API Reconnaissance (KILL SWITCH PHASE, do this first, timebox: ~1 hour)

Before building anything, verify that the data we need is actually accessible. Endpoint details below are believed correct but MUST be verified live, they may have changed.

### Polymarket
- Expected: Gamma API (`https://gamma-api.polymarket.com`) for market metadata including resolved markets (question text, outcome, category, close time, resolution), and the CLOB API (`https://clob.polymarket.com`) for historical price data. Prices are in USDC, 0.00 to 1.00, directly interpretable as implied probability.
- Verify: can we list resolved markets with pagination? Can we pull a daily (or finer) price history for a given market? What date range is available? Is any auth required for read-only endpoints?

### Kalshi
- Expected: REST API (base URL currently under `api.elections.kalshi.com/trade-api/v2` or similar) with endpoints for markets, events, and historical candlesticks. Contract prices in cents, 1 to 99, implied probability = price / 100.
- Verify: which endpoints work without an account or API key? If read access requires a free account and key, creating one is Sean's job, not yours: STOP and tell him exactly what to create and where to put the key (environment variable, never committed). Do not create accounts and never handle his password.

### Phase 0 deliverable
A short `reports/phase0_recon.md` stating for each platform: what works, what needs auth, available history depth, estimated number of resolved markets obtainable, and a GO / NO-GO call. 

**Kill switch:** If either platform's historical data is effectively inaccessible, STOP the project and report back with options rather than building around fake or synthetic data. A fallback single-platform version (calibration study on whichever platform works, dropping cross-platform divergence) is acceptable but is Sean's call, not yours.

---

## 3. Phase 1: Data Ingestion

### Target dataset
- All resolvable-to-binary resolved markets from both platforms over the largest practical window (aim for 12+ months, more if cheap). Target scale: thousands of contracts total, ideally 5,000+.
- For each contract, store: platform, platform-native ID, question/title text, category/tags, open time, close time, resolution time, final outcome (YES/NO), and any volume/liquidity fields available.
- Price history: daily closing/last price minimum; hourly or finer for markets used in the divergence study if the API allows. Store both mid/last price AND bid/ask where available (bid/ask matters for the backtest later).

### Schema (SQLite)
- `markets(platform, market_id, title, category, open_ts, close_ts, resolve_ts, outcome, volume, raw_json)`
- `prices(platform, market_id, ts, price, bid, ask, volume)`
- `matches(match_id, polymarket_id, kalshi_id, method, score, human_verified)`
- Primary keys and indexes on (platform, market_id) and (platform, market_id, ts).

### Requirements
- Idempotent ingestion: re-running never duplicates rows.
- Raw JSON responses archived to `data/raw/` before any parsing, so parsing bugs never require re-downloading.
- A `marketlens ingest --platform polymarket --since 2025-01-01` style CLI.
- Data quality report after ingestion: row counts, date coverage, % missing prices, outcome distribution, category breakdown. Write it to `reports/data_quality.md` and explain anything weird.

### Multi-outcome markets
Many markets are multi-outcome (e.g., "Who wins the nomination" with 8 candidates). Each outcome typically trades as its own binary contract. Treat each binary leg as its own row. Note in LIMITATIONS.md that legs of the same event are statistically dependent, which matters for error bars.

---

## 4. Phase 2: Cross-Platform Contract Matching

This is the genuinely hard engineering problem in the project. The same real-world event trades under different titles, e.g., "Will the Fed cut rates in September?" vs "Fed decreases rates at Sept meeting?". Build it in stages:

1. **Blocking:** only compare contracts whose close dates are within a few days of each other and, where categories exist, in compatible categories. This keeps the comparison set small.
2. **Fuzzy text matching:** normalized token-based similarity (rapidfuzz `token_set_ratio` or similar) on cleaned titles. Tune the threshold on a labeled sample.
3. **Semantic matching (optional upgrade):** if fuzzy matching recall is poor, add embedding-based similarity using a small local sentence-embedding model. Only do this if it measurably helps; do not add it for resume decoration.
4. **Human-in-the-loop verification:** ALL matches used in the divergence and arbitrage analyses must be human-verified. Emit `reports/match_candidates.csv` with both titles, dates, similarity score, and an empty `verified` column for Sean to fill in. High-precision beats high-recall here: 100 verified true pairs is a great dataset, 500 pairs at 90% precision is a poisoned one.

**Critical subtlety to check per match and document:** resolution criteria can differ between platforms even when titles look identical (different data sources, different deadlines, different edge-case rules). A "same event" pair with different resolution rules is not an arbitrage pair, it is basis risk. Flag pairs where descriptions suggest differing criteria. Explain this concept to Sean, it is a favorite interview follow-up.

Deliverable: `matches` table populated, precision estimate on a hand-labeled sample, short writeup of the matching approach and its measured accuracy.

---

## 5. Phase 3: Calibration Analysis (per platform)

Concepts to implement, each as a small tested function, each explained to Sean in plain language:

1. **Calibration curve:** bucket contracts by market-implied probability at a fixed horizon before resolution (e.g., price at 7 days out, and separately at 24 hours out). For each bucket, compare mean implied probability vs empirical resolution frequency. Plot with Wilson-score confidence intervals per bucket. Perfect calibration = diagonal line.
2. **Brier score and Murphy decomposition:** overall Brier score, decomposed into reliability (calibration error, lower is better), resolution (how much probabilities discriminate, higher is better), and uncertainty (base rate variance, a property of the event set). Compare platforms and compare horizons (7 days out vs 24 hours out: markets should sharpen as resolution approaches).
3. **Favorite-longshot bias test:** examine low-probability buckets (under ~10 cents) and high-probability buckets (over ~90 cents) specifically. The documented bias: longshots resolve YES less often than their price implies (overpriced), heavy favorites resolve YES more often than implied (underpriced). Quantify the effect size and its confidence interval, per platform.
4. **Cuts:** repeat headline analyses by category (politics, sports, econ, crypto) and by liquidity/volume tercile. Hypothesis worth testing: thin markets are worse calibrated.

Statistical hygiene: report bucket sample sizes, use proper binomial confidence intervals, and note the dependence problem (multi-leg events, correlated political outcomes) in LIMITATIONS.md rather than pretending observations are i.i.d.

Deliverables: `reports/figures/` calibration plots per platform and horizon, a results table, and a plain-English findings section in `reports/results.md` (e.g., "Polymarket contracts priced at 5 cents resolved YES only 2.8% of the time, consistent with favorite-longshot bias").

---

## 6. Phase 4: Divergence Analysis (matched pairs)

For every human-verified matched pair, align price histories on a common time index and compute:

1. **Spread series:** `spread(t) = price_polymarket(t) - price_kalshi(t)` in probability points. Summary stats: mean absolute spread, max spread, % of time |spread| exceeds 2, 5, and 10 points.
2. **Convergence behavior:** when a large divergence opens (define threshold, e.g., 5+ points), how long until it halves? Estimate a convergence half-life per pair (fit exponential decay to |spread| after divergence events, or use the empirical median time-to-half). Explain half-life to Sean with the radioactive decay analogy.
3. **Lead-lag (nice-to-have):** cross-correlate the two price series at small lags to test whether one platform systematically moves first. Interesting if present, fine if inconclusive.
4. **Divergence anatomy:** do spreads cluster around news events (visible as simultaneous large price moves)? At minimum, plot a few case-study pairs with both price series overlaid, annotated.

Deliverables: divergence summary table across all pairs, distribution plot of spreads, half-life estimates with uncertainty, 3 to 5 annotated case-study charts. These case-study charts are the single most interview-useful artifact in the project, make them clean.

---

## 7. Phase 5: Fee-Adjusted Arbitrage Backtest

The economic question: when platforms disagree, was there free money after costs? The honest expected answer is "rarely, and less than it looks," which is a legitimate market-efficiency finding.

### Strategy definition (keep it this simple)
For a matched pair at time t, if you can buy YES on the cheaper platform and NO on the other platform such that total cost per $1 of guaranteed payout is under $1 after fees, that is a theoretical arbitrage (assuming identical resolution criteria, see basis-risk caveat). Hold both legs to resolution, collect $1 on exactly one leg.

### Cost model (config-driven, documented, conservative)
- **Kalshi fees:** implement the published trading fee formula (historically on the order of `0.07 * price * (1 - price)` per contract, rounded up). VERIFY the current fee schedule from Kalshi's documentation during Phase 0 and put the formula in `config.yaml` with a source link and retrieval date.
- **Polymarket costs:** verify current trading fee status during Phase 0 (historically low/zero explicit trading fees, but confirm) and include a configurable spread/slippage haircut.
- **Execution realism:** use bid/ask when available (buy at ask), never mid. If only last-trade prices exist, apply a configurable slippage assumption (e.g., 1 point per leg) and state it. Add a configurable minimum executable size consideration in LIMITATIONS.md (thin books mean the displayed price may be good for $50, not $5,000).
- **Capital lockup:** money is tied up until resolution. Report returns both per-trade and annualized given actual time-to-resolution, because 2% locked for 9 months is not exciting and the analysis should say so.

### Backtest mechanics
- Point-in-time discipline: at each decision timestamp, use only data available at that timestamp. No lookahead. Explain lookahead bias to Sean, it is a guaranteed interview topic.
- Entry rule: enter when fee-adjusted combined cost < $1 minus a configurable edge threshold. Exit: hold to resolution (keep v1 simple, no early unwinds).
- Outputs: number of opportunities found, hit rate, P&L distribution, total and annualized return under the stated cost assumptions, and a sensitivity table showing how results change as the slippage assumption sweeps from 0 to 3 points. The sensitivity table is the rigor centerpiece: it shows whether the "profit" is real or an artifact of optimistic assumptions.

Deliverable: `reports/results.md` section with the headline finding stated honestly, e.g., "Of N matched pairs, gross arbitrage appeared in X% of pair-days; after fees and 1-point slippage per leg, exploitable opportunities fell to Y%, with median annualized return of Z%."

---

## 8. Phase 6 (Tier 3 lite, stretch): Does anything beat the price?

Scope this deliberately small. Question: does a simple model with extra features predict resolution better than the market price alone?

- **Baseline model:** predict resolution using market price alone (the price IS a probability forecast; its log-loss/Brier is the bar to beat).
- **Feature model:** logistic regression (yes, logistic regression, it is explainable) using: market price, price momentum over trailing 7 days, volume/liquidity, days-to-resolution, category dummies, and platform.
- **Evaluation:** temporal split (train on markets resolving before date T, test on markets resolving after), compare log-loss and Brier vs the price-only baseline, with a calibration curve for the model.
- **Honest framing:** the expected result is that extra features add little or nothing beyond price for most categories. If a pocket of predictability shows up (e.g., the longshot-bias correction improves low-price buckets), that is the interesting finding. Report either outcome truthfully.

Do NOT expand this into deep learning, news scraping, or LLM features in v1. Write those down in a `FUTURE.md` instead.

---

## 9. Final Deliverables Checklist

- [ ] Working pipeline: one command (`marketlens run-all` or a Makefile) reproduces the entire analysis from cached raw data.
- [ ] `README.md`: project summary, architecture diagram (ASCII or image), headline findings with 3 or 4 key figures embedded, how-to-run, tech stack. Written so a recruiter skimming for 45 seconds gets the point.
- [ ] `reports/results.md`: full findings write-up in plain language with all figures.
- [ ] `LIMITATIONS.md`: basis risk in matching, dependence between contracts, execution realism, survivorship/coverage gaps in the data, anything else discovered. Maintained throughout, not written last-minute.
- [ ] `sql/example_queries.sql`: at least 5 real analytical queries (joins, aggregations, window functions) used in the analysis.
- [ ] Tests passing, `pytest` green.
- [ ] 3 to 5 polished case-study charts.
- [ ] `INTERVIEW_PREP.md`: see section 10.

## 10. Interview Prep Appendix (generate as INTERVIEW_PREP.md at the end)

Generate a Q&A document Sean will study, covering at minimum:
- Walk me through the architecture end to end.
- What is a Brier score and what does its decomposition tell you?
- What is the favorite-longshot bias and did you find it?
- Why might two platforms price the same event differently?
- Why doesn't the arbitrage survive fees? Walk through the cost math on a concrete example from your data.
- What is lookahead bias and how did your backtest avoid it?
- What is basis risk in your matched pairs?
- What was the hardest engineering problem? (expected answer: cross-platform entity matching and building point-in-time-correct price alignment)
- What would you build next with more time?
- Biggest limitation of your results?

Each answer: 4 to 8 sentences, in Sean's voice, grounded in the actual numbers the project produced.

## 11. Working Agreement with Claude Code

- Work phase by phase. At each phase boundary, summarize findings in plain English and wait for Sean's go-ahead before the next phase.
- Prefer boring, explainable, well-tested code over clever code.
- If real data contradicts an assumption in this spec (e.g., far fewer matchable pairs than hoped), surface it immediately with options instead of silently working around it.
- All numbers in reports must come from the actual data. Never fabricate, extrapolate, or placeholder a statistic. If a number is provisional, label it provisional.
- Keep a running `WORKLOG.md`: date, what was done, decisions made, open questions. This doubles as Sean's memory when he returns to the project after a break.
