"""Data quality report: computes the numbers, renders markdown.

Pure helpers (percent, coverage_ratio) are unit-tested; SQL aggregation
functions take a connection and return plain dicts so they stay easy to test
on a small seeded database.
"""

from __future__ import annotations

import sqlite3
from typing import Any

PLATFORMS = ("polymarket", "kalshi")


def percent(part: float, whole: float) -> float:
    """Percentage safe against zero denominators, rounded to 2 decimals."""
    if whole == 0:
        return 0.0
    return round(100.0 * part / whole, 2)


def coverage_ratio(price_days: int, lifetime_days: float) -> float:
    """Fraction of a market's lifetime covered by daily price rows, capped at 1."""
    if lifetime_days <= 0:
        return 1.0 if price_days > 0 else 0.0
    return min(1.0, price_days / lifetime_days)


def market_counts(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for p in PLATFORMS:
        total = conn.execute(
            "SELECT COUNT(*) FROM markets WHERE platform = ?", (p,)).fetchone()[0]
        headline = conn.execute(
            "SELECT COUNT(*) FROM headline_markets WHERE platform = ?", (p,)).fetchone()[0]
        no_outcome = conn.execute(
            "SELECT COUNT(*) FROM markets WHERE platform = ? AND outcome IS NULL",
            (p,)).fetchone()[0]
        short = conn.execute(
            """SELECT COUNT(*) FROM markets
               WHERE platform = ? AND outcome IN ('YES','NO')
                 AND open_ts IS NOT NULL AND close_ts IS NOT NULL
                 AND (julianday(close_ts) - julianday(open_ts)) * 24.0 < 24.0""",
            (p,)).fetchone()[0]
        out[p] = {"total": total, "headline": headline,
                  "excluded_no_outcome": no_outcome, "excluded_short": short}
    return out


def date_coverage(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in PLATFORMS:
        lo, hi = conn.execute(
            "SELECT MIN(close_ts), MAX(close_ts) FROM headline_markets WHERE platform = ?",
            (p,)).fetchone()
        monthly = conn.execute(
            """SELECT substr(close_ts, 1, 7) AS month, COUNT(*)
               FROM headline_markets WHERE platform = ?
               GROUP BY month ORDER BY month""", (p,)).fetchall()
        out[p] = {"min_close": lo, "max_close": hi, "monthly": monthly}
    return out


def outcome_distribution(conn: sqlite3.Connection) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for p in PLATFORMS:
        rows = conn.execute(
            """SELECT outcome, COUNT(*) FROM headline_markets
               WHERE platform = ? GROUP BY outcome""", (p,)).fetchall()
        out[p] = {str(k): v for k, v in rows}
    return out


def category_breakdown(conn: sqlite3.Connection, top_n: int = 15) -> dict[str, list]:
    out: dict[str, list] = {}
    for p in PLATFORMS:
        rows = conn.execute(
            """SELECT COALESCE(category, '(none)') AS cat, COUNT(*) AS n
               FROM headline_markets WHERE platform = ?
               GROUP BY cat ORDER BY n DESC LIMIT ?""", (p, top_n)).fetchall()
        out[p] = rows
    return out


def price_stats(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Price coverage among markets that have any price rows.

    missing percentage is computed against each market's lifetime in days,
    since prices are daily: a 100-day market with 80 rows is 20% missing.
    """
    out: dict[str, dict[str, Any]] = {}
    for p in PLATFORMS:
        n_rows, n_markets = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT market_id) FROM prices WHERE platform = ?",
            (p,)).fetchone()
        null_price = conn.execute(
            "SELECT COUNT(*) FROM prices WHERE platform = ? AND price IS NULL",
            (p,)).fetchone()[0]
        per_market = conn.execute(
            """SELECT COUNT(pr.ts) AS days,
                      (julianday(m.close_ts) - julianday(m.open_ts)) AS lifetime_days
               FROM prices pr
               JOIN markets m ON m.platform = pr.platform AND m.market_id = pr.market_id
               WHERE pr.platform = ?
               GROUP BY pr.market_id""", (p,)).fetchall()
        ratios = [coverage_ratio(days, life or 0) for days, life in per_market]
        avg_cov = round(sum(ratios) / len(ratios), 4) if ratios else None
        out[p] = {
            "price_rows": n_rows,
            "markets_with_prices": n_markets,
            "null_price_rows": null_price,
            "pct_null_price_rows": percent(null_price, n_rows),
            "avg_lifetime_coverage": avg_cov,
        }
    return out


def render_report(conn: sqlite3.Connection) -> str:
    mc = market_counts(conn)
    dc = date_coverage(conn)
    od = outcome_distribution(conn)
    cb = category_breakdown(conn)
    ps = price_stats(conn)

    lines: list[str] = []
    add = lines.append
    add("# Data Quality Report")
    add("")
    add("Generated by `marketlens quality-report`. Headline dataset = resolved")
    add("binary markets with lifetime of 24 hours or more (Sean's inclusion")
    add("decision, 2026-07-09), within the configured ingestion frame.")
    add("")
    add("## Row counts")
    add("")
    add("| Platform | Markets ingested | Headline markets | No clean outcome | Resolved but sub-24h |")
    add("|---|---|---|---|---|")
    for p in PLATFORMS:
        c = mc[p]
        add(f"| {p} | {c['total']:,} | {c['headline']:,} | "
            f"{c['excluded_no_outcome']:,} | {c['excluded_short']:,} |")
    add("")
    add("## Date coverage (headline markets, by close month)")
    for p in PLATFORMS:
        d = dc[p]
        add("")
        add(f"### {p}: {d['min_close']} to {d['max_close']}")
        add("")
        add("| Month | Markets |")
        add("|---|---|")
        for month, n in d["monthly"]:
            add(f"| {month} | {n:,} |")
    add("")
    add("## Outcome distribution (headline markets)")
    add("")
    add("| Platform | YES | NO | YES share |")
    add("|---|---|---|---|")
    for p in PLATFORMS:
        y, n = od[p].get("YES", 0), od[p].get("NO", 0)
        add(f"| {p} | {y:,} | {n:,} | {percent(y, y + n)}% |")
    add("")
    add("## Category breakdown (headline markets, top 15)")
    for p in PLATFORMS:
        add("")
        add(f"### {p}")
        add("")
        add("| Category | Markets |")
        add("|---|---|")
        for cat, n in cb[p]:
            add(f"| {cat} | {n:,} |")
    add("")
    add("## Price coverage (sampled markets)")
    add("")
    add("| Platform | Price rows | Markets with prices | Null-price rows | % null | Avg lifetime coverage |")
    add("|---|---|---|---|---|---|")
    for p in PLATFORMS:
        s = ps[p]
        cov = s["avg_lifetime_coverage"]
        add(f"| {p} | {s['price_rows']:,} | {s['markets_with_prices']:,} | "
            f"{s['null_price_rows']:,} | {s['pct_null_price_rows']}% | "
            f"{cov if cov is not None else 'n/a'} |")
    add("")
    add("Null-price rows are Kalshi candle periods with no trades; those rows")
    add("still carry closing bid/ask, so downstream code uses")
    add("COALESCE(price, (bid + ask) / 2.0). Polymarket history has no bid/ask.")
    add("")
    add(NOTES)
    return "\n".join(lines)


# Interpretive notes that travel with the generated tables. These are
# regenerated with the report so a rerun cannot silently drop them; the
# full caveat list lives in LIMITATIONS.md.
NOTES = """## How to read these tables

- **Kalshi's usable window is far shorter than Polymarket's.** The
  monthly coverage table shows why: Kalshi's trade API purges older
  settled markets, so despite a 24-month ingestion window its resolved
  data effectively begins in May 2026. Pre-May rows that survive mostly
  lack a result and are excluded from the headline set. Cross-platform
  comparisons inherit this mismatch.
- **March 2026 is under-covered on Polymarket**, an upstream hole in the
  Gamma API verified by live re-queries, not an ingestion failure.
- **A handful of Polymarket markets close before the ingestion window
  starts.** The frame keys on scheduled end date, but a market that
  resolves early stops trading at its closedTime, which can precede the
  window.
- **A YES share near one third is expected, not a red flag.**
  Multi-outcome events list one binary leg per candidate and at most one
  leg resolves YES, which pulls the base rate well below one half. The
  two platforms landing within a point of each other is a mild sanity
  check on outcome parsing.
- **Sports dominates both platforms**, so pooled results are effectively
  sports-weighted unless reported per category, which the calibration
  analysis does.
- **Polymarket categories are messy** because they derive from tags:
  Bitcoin, Ethereum, Solana and XRP appear alongside a generic Crypto
  tag. Analysis code maps them to coarse buckets before any category
  cut."""
