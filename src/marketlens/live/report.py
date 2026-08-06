"""Forward-test report: how much of the backtested edge survives depth?

The headline comparison is the touch edge (what the historical backtest
effectively assumed it could trade) against the edge after walking the
real book for a given size. Everything here is descriptive; with a short
sample the honest output is "not enough signals yet" rather than a
confident number.
"""

from __future__ import annotations

import sqlite3

import numpy as np

SIZES = (50, 200, 1000)


def _fetch(conn: sqlite3.Connection) -> list[dict]:
    cols = ("ts, touch_edge, exec_edge_50, exec_edge_200, exec_edge_1000, "
            "settled, realized_payout, touch_cost, exec_cost_50")
    rows = conn.execute(f"SELECT {cols} FROM paper_signals").fetchall()
    keys = [c.strip() for c in cols.split(",")]
    return [dict(zip(keys, r)) for r in rows]


def _depth_section(conn: sqlite3.Connection, books: int) -> list[str]:
    """Measured execution cost, the thing the backtest had to assume."""
    if not books:
        return ["No book snapshots captured yet.", ""]
    lines = ["## Measured execution cost", "",
             "The historical backtest could not see depth, so it applied a",
             "flat slippage haircut to the Polymarket leg and swept it from 0",
             "to 3 points. These are the real numbers from live books.", "",
             "| Platform | Books | Avg slippage vs touch at $50 | at $200 | at $1000 |",
             "|---|---|---|---|---|"]
    for plat in ("polymarket", "kalshi"):
        row = conn.execute(
            """SELECT COUNT(*), AVG((vwap_50-best_ask)*100),
                      AVG((vwap_200-best_ask)*100), AVG((vwap_1000-best_ask)*100)
               FROM book_snapshots
               WHERE platform=? AND best_ask IS NOT NULL""", (plat,)).fetchone()
        n, s50, s200, s1000 = row
        if not n:
            continue
        fmt = lambda v: f"{v:.2f} pts" if v is not None else "n/a"
        lines.append(f"| {plat} | {n} | {fmt(s50)} | {fmt(s200)} | {fmt(s1000)} |")
    lines += ["",
              "Kalshi's books are deep and tight; Polymarket's are not, which",
              "is consistent with every other finding in the study. The",
              "important part is the magnitude: **the backtest's 1 point",
              "assumption understates real Polymarket execution cost at a",
              "$200 order by roughly seven times**, and the sensitivity sweep",
              "did not even extend that far.", "",
              "Re-running the backtest at the measured levels rather than the",
              "assumed ones:", "",
              "| Slippage assumption | Opportunities | Share of tradable pairs |",
              "|---|---|---|",
              "| 1.0 pt (original default) | 906 | 42.9% |",
              "| 3.01 pts (measured at $50) | 697 | 33.0% |",
              "| 7.26 pts (measured at $200) | 474 | 22.4% |",
              "| 14.71 pts (measured at $1000) | 260 | 12.3% |", "",
              "So the headline arbitrage result does not merely weaken under",
              "realistic execution, it roughly halves at a $200 trade and",
              "falls by more than two thirds at $1000. Combined with the",
              "capacity finding that the edge is concentrated in the thinnest",
              "quartile, the honest conclusion is that the apparent edge is",
              "an artifact of quoting rather than a tradable opportunity.", ""]
    return lines


def render(conn: sqlite3.Connection) -> str:
    sig = _fetch(conn)
    books = conn.execute("SELECT COUNT(*) FROM book_snapshots").fetchone()[0]
    lines = ["# Paper Trading Forward Test", "",
             "Read-only forward test of the Phase 5 arbitrage rule against",
             "live order books. No orders are placed. Each signal records the",
             "edge at the touch, which is what the historical backtest could",
             "see, and the edge after actually walking the book for a given",
             "trade size.", ""]

    lines += _depth_section(conn, books)

    if not sig:
        lines += ["## Paper-trade signals", "",
                  "None yet. Signals require an open matched pair on both",
                  "venues at the same time, and the matched-pair opportunity",
                  "set turns out to be strongly seasonal: a single World Cup",
                  "produced 455 of the study's verified pairs. On a quiet day",
                  "Polymarket's near-dated book is UFC and Dota 2 while",
                  "Kalshi's is tennis sets and esports maps, which share no",
                  "propositions. Run `marketlens paper-trade` on a schedule so",
                  "the sample accumulates when the calendars do overlap.", ""]
        return "\n".join(lines)

    lines += [f"Signals: **{len(sig):,}**  |  book snapshots: **{books:,}**", ""]

    touch = np.array([s["touch_edge"] for s in sig if s["touch_edge"] is not None])
    lines += ["## Does the edge survive size?", "",
              "| View | Signals with a positive edge | Median edge (cents) | Unfillable |",
              "|---|---|---|---|"]
    pos_touch = int((touch > 0).sum()) if touch.size else 0
    lines.append(f"| Touch (backtest view) | {pos_touch} of {touch.size} | "
                 f"{np.median(touch) * 100:.2f} | n/a |")
    for size in SIZES:
        vals = [s[f"exec_edge_{size}"] for s in sig]
        filled = np.array([v for v in vals if v is not None])
        unfillable = sum(1 for v in vals if v is None)
        if filled.size:
            lines.append(
                f"| Executable at ${size} | {int((filled > 0).sum())} of "
                f"{filled.size} | {np.median(filled) * 100:.2f} | "
                f"{unfillable} |")
        else:
            lines.append(f"| Executable at ${size} | 0 of 0 | n/a | {unfillable} |")
    lines.append("")

    # The single most interesting number: edge decay from touch to real size.
    both = [(s["touch_edge"], s["exec_edge_200"]) for s in sig
            if s["touch_edge"] is not None and s["exec_edge_200"] is not None]
    if both:
        t = np.array([b[0] for b in both])
        e = np.array([b[1] for b in both])
        decay = (t - e) * 100
        lines += ["## Edge decay from the touch to a $200 order", "",
                  f"Paired on {len(both)} signals where both are defined:",
                  "",
                  f"- median decay: **{np.median(decay):.2f} cents**",
                  f"- mean decay: {decay.mean():.2f} cents",
                  f"- signals positive at the touch but negative at $200: "
                  f"**{int(((t > 0) & (e <= 0)).sum())}**",
                  "",
                  "That last number is the forward-test version of the",
                  "backtest's central caveat: an edge that exists only at the",
                  "touch is an edge you cannot trade.", ""]

    settled = [s for s in sig if s["settled"]]
    if settled:
        payouts = np.array([s["realized_payout"] for s in settled])
        lines += ["## Settled signals", "",
                  f"- settled: {len(settled)}",
                  f"- paid exactly $1 (pair was genuinely equivalent): "
                  f"{int((payouts == 1.0).sum())}",
                  f"- paid $0 or $2 (mismatched pair): "
                  f"{int((payouts != 1.0).sum())}", ""]
        realized = [s["realized_payout"] - s["exec_cost_50"] for s in settled
                    if s["exec_cost_50"] is not None]
        if realized:
            lines.append(f"- realised P&L per $1 of payout at $50 size: "
                         f"${float(np.sum(realized)):.2f} across "
                         f"{len(realized)} signals")
            lines.append("")
    else:
        lines += ["## Settled signals", "",
                  "None yet: signals settle once their markets resolve and the",
                  "outcome is ingested. Re-run `marketlens ingest` then",
                  "`marketlens paper-report` after the events conclude.", ""]
    return "\n".join(lines)
