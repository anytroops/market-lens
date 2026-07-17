"""Typer CLI entry point.

Examples:
    marketlens init-db
    marketlens ingest --platform polymarket --since 2024-07-09
    marketlens ingest --platform kalshi --stage metadata
    marketlens quality-report
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from marketlens.config import load_config
from marketlens.db import schema
from marketlens.ingest import runner

app = typer.Typer(help="market-lens data pipeline")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def _connect(config: str):
    cfg = load_config(config)
    conn = schema.connect(cfg.db_path(), cfg.ingestion.min_lifetime_hours)
    return cfg, conn


@app.command()
def init_db(config: str = "config.yaml") -> None:
    """Create the SQLite database and tables."""
    cfg, conn = _connect(config)
    conn.close()
    typer.echo(f"database ready at {cfg.db_path()}")


@app.command()
def ingest(
    platform: str = typer.Option(..., help="polymarket, kalshi, or all"),
    since: str = typer.Option(None, help="ISO date, defaults to config"),
    until: str = typer.Option(None, help="ISO date, defaults to config"),
    stage: str = typer.Option("all", help="metadata, prices, or all"),
    max_markets: int = typer.Option(None, help="cap for smoke tests"),
    config: str = "config.yaml",
) -> None:
    """Ingest resolved markets and price histories into SQLite."""
    if platform not in ("polymarket", "kalshi", "all"):
        raise typer.BadParameter("platform must be polymarket, kalshi, or all")
    if stage not in ("metadata", "prices", "all"):
        raise typer.BadParameter("stage must be metadata, prices, or all")
    cfg, conn = _connect(config)
    platforms = ["polymarket", "kalshi"] if platform == "all" else [platform]
    for p in platforms:
        if stage in ("metadata", "all"):
            if p == "polymarket":
                runner.ingest_polymarket_metadata(cfg, conn, since, until, max_markets)
            else:
                runner.ingest_kalshi_metadata(cfg, conn, since, until, max_markets)
        if stage in ("prices", "all"):
            if p == "polymarket":
                runner.ingest_polymarket_prices(cfg, conn, max_markets)
            else:
                runner.ingest_kalshi_prices(cfg, conn, max_markets)
    conn.close()


@app.command()
def match(
    since: str = typer.Option("2026-04-28", help="close date lower bound (ISO)"),
    until: str = typer.Option(None, help="close date upper bound, defaults to config until"),
    threshold: float = typer.Option(85.0, help="token_set_ratio cutoff, 0 to 100"),
    window_days: int = typer.Option(3, help="max close-date difference in days"),
    out: str = "reports/match_candidates.csv",
    config: str = "config.yaml",
) -> None:
    """Generate cross-platform match candidates for human verification."""
    from marketlens.matching.runner import run_matching

    cfg, conn = _connect(config)
    stats = run_matching(conn, since, until or cfg.ingestion.until,
                         threshold, window_days, cfg.root / out)
    conn.close()
    typer.echo(f"match stats: {stats}")


@app.command()
def fetch_pair_prices(config: str = "config.yaml") -> None:
    """Fetch price histories for verified matched pairs that lack them."""
    cfg, conn = _connect(config)
    pairs = conn.execute(
        "SELECT polymarket_id, kalshi_id FROM matches WHERE human_verified = 1"
    ).fetchall()
    need = {"polymarket": {p for p, _ in pairs}, "kalshi": {k for _, k in pairs}}
    for platform in ("polymarket", "kalshi"):
        have = {r[0] for r in conn.execute(
            "SELECT DISTINCT market_id FROM prices WHERE platform = ?", (platform,))}
        missing = sorted(need[platform] - have)
        typer.echo(f"{platform}: {len(missing)} verified-pair markets need prices")
        if platform == "polymarket":
            runner.ingest_polymarket_prices(cfg, conn, market_ids=missing)
        else:
            runner.ingest_kalshi_prices(cfg, conn, market_ids=missing)
    conn.close()


@app.command()
def calibrate(
    out: str = "reports/calibration_tables.md",
    config: str = "config.yaml",
) -> None:
    """Run the calibration analysis, write figures and result tables.

    The narrative findings live in reports/results.md, which is authored
    by hand and never overwritten by this command.
    """
    from marketlens.analysis.report import run_analysis

    cfg, conn = _connect(config)
    section = run_analysis(conn, cfg.root)
    conn.close()
    out_path = cfg.root / out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(section)
    typer.echo(f"wrote {out_path}")


@app.command()
def diverge(
    out_csv: str = "reports/divergence_pairs.csv",
    out_md: str = "reports/divergence_tables.md",
    config: str = "config.yaml",
) -> None:
    """Divergence analysis over verified matched pairs (Phase 4)."""
    import json as _json

    from marketlens.analysis import divergence as dv
    from marketlens.analysis.divergence_report import (
        aggregate_summary, build_pair_table, load_daily_prices)
    from marketlens.viz import plots

    cfg, conn = _connect(config)
    table = build_pair_table(conn)
    if table.empty:
        typer.echo("no pairs with overlapping prices; run fetch-pair-prices first")
        raise typer.Exit(1)

    csv_table = table.copy()
    csv_table["half_lives"] = csv_table["half_lives"].map(_json.dumps)
    csv_table.sort_values("mean_abs", ascending=False).to_csv(
        cfg.root / out_csv, index=False)

    agg = aggregate_summary(table)
    agg_nb = aggregate_summary(table[table["basis_risk"] == 0])
    fig_dir = cfg.root / "reports" / "figures"
    plots.spread_distribution(
        table["mean_abs"].tolist(),
        f"Cross-platform divergence, {agg['pairs']:,} verified pairs",
        fig_dir / "spread_distribution.png")

    # Case studies: long-overlap, liquid, interesting pairs, diverse categories.
    cs = table[(table["n_days"] >= 10) & (table["max_abs"] >= 6)]
    cs = cs.sort_values("volume", ascending=False)
    picked, seen_cat = [], set()
    for _, row in cs.iterrows():
        if row["category"] in seen_cat and len(seen_cat) < 3:
            continue
        picked.append(row)
        seen_cat.add(row["category"])
        if len(picked) == 5:
            break
    pm_prices = load_daily_prices(conn, "polymarket", {r["pm_id"] for r in picked})
    k_prices = load_daily_prices(conn, "kalshi", {r["kalshi_id"] for r in picked})
    for i, row in enumerate(picked, 1):
        df = dv.align_pair(pm_prices[row["pm_id"]], k_prices[row["kalshi_id"]],
                           row["orientation"] or "same")
        ann = (f"mean |spread| {row['mean_abs']:.1f} pts, max {row['max_abs']:.1f}, "
               f"{row['n_days']} common days, category {row['category']}"
               + (", basis-risk pair" if row["basis_risk"] else ""))
        plots.pair_case_study(df, row["pm_title"], row["k_title"], ann,
                              fig_dir / f"case_study_{i}.png")

    lines = ["# Divergence Tables (generated)", ""]
    lines.append("| Metric | All verified pairs | Excluding basis risk |")
    lines.append("|---|---|---|")
    for key in agg:
        lines.append(f"| {key} | {agg[key]} | {agg_nb[key]} |")
    lines.append("")
    lines.append("Per-pair detail in divergence_pairs.csv; case studies in figures/.")
    (cfg.root / out_md).write_text("\n".join(lines))
    conn.close()
    typer.echo(f"pairs analyzed: {agg['pairs']}, wrote {out_csv}, {out_md}, "
               f"{len(picked)} case studies")


@app.command()
def quality_report(
    out: str = "reports/data_quality.md",
    config: str = "config.yaml",
) -> None:
    """Write the data quality report to reports/data_quality.md."""
    from marketlens.quality import render_report

    cfg, conn = _connect(config)
    report = render_report(conn)
    conn.close()
    out_path = cfg.root / out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    typer.echo(f"wrote {out_path}")


if __name__ == "__main__":
    app()
