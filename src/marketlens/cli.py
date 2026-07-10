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
