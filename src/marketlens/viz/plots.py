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
