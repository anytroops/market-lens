"""Matplotlib figures for the reports.

Style follows the dataviz method: one hue per figure from a validated
palette, recessive grid and axes, direct labels over legends where
possible, Wilson error bars, and a sample-size strip under every
reliability diagram so bucket credibility is visible at a glance.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from marketlens.analysis.calibration import CalibrationBin

PALETTE = {"polymarket": "#2a78d6", "kalshi": "#1baf7a"}  # validated slots 1, 2
GRID = "#d9d9d4"
INK = "#333230"
MUTED = "#6f6e66"


def _style_axes(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.6)
    ax.set_axisbelow(True)


def spread_distribution(mean_abs: list[float], title: str, path: Path) -> None:
    """Histogram of per-pair mean absolute spreads in probability points."""
    fig, ax = plt.subplots(figsize=(6.4, 4))
    ax.hist(mean_abs, bins=40, color=PALETTE["polymarket"], alpha=0.8)
    ax.set_xlabel("Mean |spread| per pair (probability points)", fontsize=10,
                  color=INK)
    ax.set_ylabel("Pairs", fontsize=10, color=INK)
    ax.set_title(title, fontsize=12, color=INK, loc="left")
    _style_axes(ax)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def pair_case_study(df, pm_title: str, k_title: str, annotation: str,
                    path: Path) -> None:
    """Overlaid daily price series for one matched pair plus spread strip."""
    fig, (ax, axs) = plt.subplots(
        2, 1, figsize=(7.6, 5.6), height_ratios=[3, 1], sharex=True,
        gridspec_kw={"hspace": 0.1})
    x = list(df.index)
    ax.plot(x, df["pm"], color=PALETTE["polymarket"], linewidth=2,
            label="Polymarket")
    ax.plot(x, df["kalshi"], color=PALETTE["kalshi"], linewidth=2,
            label="Kalshi")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Implied probability", fontsize=10, color=INK)
    ax.legend(frameon=False, fontsize=9, loc="best")
    title = pm_title if len(pm_title) < 70 else pm_title[:67] + "..."
    n_lines = annotation.count("\n") + 1
    ax.set_title(title, fontsize=11, color=INK, loc="left",
                 pad=10 + 11 * n_lines)
    ax.text(0, 1.02, annotation, transform=ax.transAxes, fontsize=8,
            color=MUTED, va="bottom", linespacing=1.5)
    _style_axes(ax)

    axs.fill_between(x, df["spread"], 0, color=PALETTE["polymarket"],
                     alpha=0.35, linewidth=0)
    axs.axhline(0, color=MUTED, linewidth=0.8)
    axs.set_ylabel("Spread (pts)", fontsize=8, color=MUTED)
    _style_axes(axs)
    fig.autofmt_xdate(rotation=30)

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def reliability_diagram(table: list[CalibrationBin], title: str,
                        subtitle: str, color: str, path: Path) -> None:
    """Reliability diagram with Wilson CIs plus a bin-count strip."""
    fig, (ax, axn) = plt.subplots(
        2, 1, figsize=(6.4, 6.4), height_ratios=[4, 1], sharex=True,
        gridspec_kw={"hspace": 0.08})

    ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1, color=MUTED,
            zorder=1)
    xs = [b.mean_prob for b in table]
    ys = [b.yes_rate for b in table]
    yerr_lo = [b.yes_rate - b.ci_lo for b in table]
    yerr_hi = [b.ci_hi - b.yes_rate for b in table]
    ax.errorbar(xs, ys, yerr=[yerr_lo, yerr_hi], fmt="o", markersize=6,
                color=color, ecolor=color, elinewidth=1.2, capsize=3,
                zorder=3)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Empirical YES rate", fontsize=10, color=INK)
    ax.set_title(title, fontsize=12, color=INK, loc="left", pad=14)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9,
            color=MUTED)
    _style_axes(ax)

    axn.bar([b.mean_prob for b in table], [b.n for b in table],
            width=0.06, color=color, alpha=0.55)
    axn.set_yscale("log")
    axn.set_ylabel("markets", fontsize=8, color=MUTED)
    axn.set_xlabel("Market-implied probability", fontsize=10, color=INK)
    _style_axes(axn)

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
