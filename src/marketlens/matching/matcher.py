"""Cross-platform contract matching (Phase 2).

Pipeline: blocking, fuzzy scoring, deterministic compatibility guards,
then mutual-best filtering.

- Blocking: only compare markets whose close dates are near and whose
  categories map to the same coarse bucket. This turns an infeasible
  100k x 235k comparison into millions that rapidfuzz's C++ cdist handles
  in minutes.
- Scoring: token_set_ratio on normalized titles. It treats titles as word
  sets, so word order and filler words matter little. Its weakness is the
  flip side: a title whose tokens are a subset of another's scores 100,
  so "Brazil: 5+ corners" looks identical to "Brazil vs Norway: O/U 6.5
  Total Corners".
- Guards: hand-labeling a stratified sample showed the false matches are
  systematic, so they are rejected deterministically: numeric tokens must
  agree exactly (thresholds, spreads, dates in titles), max/min temperature
  wording must agree, 1st/2nd half must agree, toss markets never match
  non-toss markets, a bare "A vs B" matchup title (a moneyline) only
  matches texts about winning, and close dates must be within a per-bucket
  window (1 day for daily sports and weather).
- Mutual best: a pair survives only if each side is the other's best
  surviving candidate. Precision over recall throughout: one false pair
  poisons the divergence study, a missed pair just shrinks it.

Kalshi quirks: multi-candidate markets repeat the event title and put the
proposition in yes_sub_title, so match text concatenates both. Weather
titles omit the city (it lives in the series ticker), so weather pairs
additionally require the city implied by the Kalshi series to appear in
the Polymarket title.

All candidates require HUMAN verification before use in divergence or
arbitrage analysis (match_candidates.csv, verified column). Verifiers must
check the PROPOSITION, not just the event, and note leg orientation: a
Polymarket "A vs B" market's stored price tracks outcome A, while the
matched Kalshi market may ask about B, in which case the pair is valid but
inverted (use 1 - p). Even verified same-event pairs can differ in
resolution criteria (data source, deadline, edge cases): that residual
risk is basis risk, tracked per pair in Phase 4.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

# Coarse category buckets. Unmapped categories fall into "other", which only
# blocks against "other", so a mapping gap costs recall, never precision.
_PM_BUCKETS = {
    "sports": "sports", "tennis": "sports", "esports": "sports",
    "soccer": "sports", "nba": "sports", "nfl": "sports", "mlb": "sports",
    "nhl": "sports", "golf": "sports", "boxing": "sports", "mma": "sports",
    "f1": "sports", "olympics": "sports",
    "crypto": "crypto", "bitcoin": "crypto", "ethereum": "crypto",
    "solana": "crypto", "xrp": "crypto", "up or down": "crypto",
    "politics": "politics", "geopolitics": "politics", "world": "politics",
    "elections": "politics", "us-current-affairs": "politics",
    "finance": "econ", "economy": "econ", "business": "econ",
    "companies": "econ", "stocks": "econ", "fed rates": "econ",
    "culture": "entertainment", "movies": "entertainment",
    "awards": "entertainment", "music": "entertainment",
    "celebrities": "entertainment", "pop culture": "entertainment",
    "tv": "entertainment", "mentions": "mentions",
    "science": "science", "tech": "science", "ai": "science",
    "health": "science", "weather": "weather", "climate": "weather",
}
_KALSHI_BUCKETS = {
    "sports": "sports",
    "crypto": "crypto",
    "politics": "politics", "elections": "politics",
    "economics": "econ", "financials": "econ", "commodities": "econ",
    "companies": "econ",
    "entertainment": "entertainment", "social": "entertainment",
    "mentions": "mentions",
    "science and technology": "science", "health": "science",
    "climate and weather": "weather", "transportation": "other",
}

# Max close-date difference per bucket. Daily sports and weather markets
# recur every day with near-identical titles, so anything beyond one day is
# almost certainly a different game or a different day's weather.
BUCKET_WINDOW_DAYS = {"sports": 1, "weather": 1}
DEFAULT_WINDOW_DAYS = 3

# City implied by a Kalshi weather series ticker, matched against the
# Polymarket title. Extend as new series appear; unknown weather series
# reject rather than guess.
KALSHI_WEATHER_CITIES = {
    "NY": "new york", "CHI": "chicago", "MIA": "miami", "AUS": "austin",
    "LAX": "los angeles", "LA": "los angeles", "PHIL": "philadelphia",
    "DEN": "denver", "HOU": "houston", "SEA": "seattle", "SFO": "san francisco",
    "SF": "san francisco", "DAL": "dallas", "PHX": "phoenix", "DC": "washington",
}

_PUNCT = re.compile(r"[^a-z0-9 .+-]+")
_SPACES = re.compile(r"\s+")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_BARE_MATCHUP = re.compile(r"^[a-z0-9 .]+ vs [a-z0-9 .]+$")
_WIN_WORDS = re.compile(r"\b(win|wins|winner|beat|beats|moneyline)\b")

_MAX_WORDS = re.compile(r"\b(highest|maximum|max|high temp)\b")
_MIN_WORDS = re.compile(r"\b(lowest|minimum|min|low temp)\b")
_FIRST_HALF = re.compile(r"\b(1st|first) half\b")
_SECOND_HALF = re.compile(r"\b(2nd|second) half\b")


def normalize_title(text: str) -> str:
    """Lowercase, strip most punctuation, collapse whitespace.

    Keeps digits, '.', '+', '-' so thresholds like 15.5, 1+, -2.5 survive.
    """
    t = _PUNCT.sub(" ", (text or "").lower())
    return _SPACES.sub(" ", t).strip()


def category_bucket(platform: str, category: str | None) -> str:
    """Map a platform-native category to a coarse blocking bucket."""
    table = _PM_BUCKETS if platform == "polymarket" else _KALSHI_BUCKETS
    return table.get((category or "").lower(), "other")


def kalshi_match_text(title: str, raw_json: str) -> str:
    """Title plus yes_sub_title when the subtitle adds information."""
    sub = ""
    try:
        sub = str(json.loads(raw_json).get("yes_sub_title") or "")
    except (TypeError, ValueError):
        pass
    if sub and normalize_title(sub) not in normalize_title(title):
        return f"{title} {sub}"
    return title


def extract_numbers(text: str) -> frozenset[float]:
    """Numeric tokens of a normalized title, excluding 4-digit years.

    These carry the proposition's thresholds, spreads, strikes, and
    in-title dates: "o u 15.5" -> {15.5}, "between 84-85 on may 31" ->
    {84, 85, 31}, "ut-01" -> {1}.
    """
    out = set()
    for tok in _NUMBER.findall(text):
        v = float(tok)
        if v.is_integer() and 1900 <= v <= 2100:
            continue
        out.add(v)
    return frozenset(out)


def _minmax_class(text: str) -> str | None:
    is_max = bool(_MAX_WORDS.search(text))
    is_min = bool(_MIN_WORDS.search(text))
    if is_max and not is_min:
        return "max"
    if is_min and not is_max:
        return "min"
    return None


def _half_class(text: str) -> str | None:
    if _FIRST_HALF.search(text):
        return "1st"
    if _SECOND_HALF.search(text):
        return "2nd"
    return None


def compatible(pm_text: str, k_text: str) -> bool:
    """Deterministic proposition-compatibility guards on normalized texts.

    Each rule was derived from a labeled false-match mode; see module
    docstring. Returns False when the two texts provably describe
    different propositions.
    """
    if extract_numbers(pm_text) != extract_numbers(k_text):
        return False
    a, b = _minmax_class(pm_text), _minmax_class(k_text)
    if a and b and a != b:
        return False
    a, b = _half_class(pm_text), _half_class(k_text)
    if a and b and a != b:
        return False
    if ("toss" in pm_text.split()) != ("toss" in k_text.split()):
        return False
    for bare, other in ((pm_text, k_text), (k_text, pm_text)):
        if _BARE_MATCHUP.match(bare) and not extract_numbers(bare):
            if not _WIN_WORDS.search(other):
                return False
    return True


def weather_city_ok(pm_text: str, kalshi_series: str | None) -> bool:
    """Weather pairs must agree on city.

    Kalshi weather titles omit the city; it is encoded in the series ticker
    (e.g. KXHIGHNY). Unknown series reject rather than guess.
    """
    if not kalshi_series:
        return False
    suffix = re.sub(r"^KX(HIGH|LOW|MIN|MAX)?(TEMP)?", "", kalshi_series.upper())
    city = KALSHI_WEATHER_CITIES.get(suffix)
    return bool(city) and city in pm_text


@dataclass(frozen=True)
class MatchInput:
    """One market prepared for matching."""
    market_id: str
    text: str
    close_date: dt.date
    bucket: str
    series: str | None = field(default=None)  # kalshi series ticker


@dataclass(frozen=True)
class Candidate:
    polymarket_id: str
    kalshi_id: str
    score: float


def _pair_ok(k: MatchInput, p: MatchInput) -> bool:
    window = BUCKET_WINDOW_DAYS.get(k.bucket, DEFAULT_WINDOW_DAYS)
    if abs((k.close_date - p.close_date).days) > window:
        return False
    if not compatible(p.text, k.text):
        return False
    if k.bucket == "weather" and not weather_city_ok(p.text, k.series):
        return False
    return True


TOP_N = 8  # guarded candidates considered per Kalshi market per block


def build_candidates(pm: list[MatchInput], k: list[MatchInput],
                     threshold: float = 85.0,
                     window_days: int = DEFAULT_WINDOW_DAYS) -> list[Candidate]:
    """Blocked fuzzy matching with compatibility guards and mutual best.

    window_days bounds the blocking join; the per-bucket rule in _pair_ok
    can only tighten it further.
    """
    pm_by_key: dict[tuple[dt.date, str], list[MatchInput]] = defaultdict(list)
    for p in pm:
        pm_by_key[(p.close_date, p.bucket)].append(p)

    k_by_key: dict[tuple[dt.date, str], list[MatchInput]] = defaultdict(list)
    for m in k:
        k_by_key[(m.close_date, m.bucket)].append(m)

    k_best: dict[str, tuple[str, float]] = {}
    pm_best: dict[str, tuple[str, float]] = {}
    for (day, bucket), k_items in k_by_key.items():
        pm_items: list[MatchInput] = []
        for delta in range(-window_days, window_days + 1):
            pm_items.extend(pm_by_key.get((day + dt.timedelta(days=delta), bucket), []))
        if not pm_items:
            continue
        scores = process.cdist(
            [m.text for m in k_items], [p.text for p in pm_items],
            scorer=fuzz.token_set_ratio, score_cutoff=threshold, workers=-1,
        )
        top_n = min(TOP_N, len(pm_items))
        for i, m in enumerate(k_items):
            row = scores[i]
            order = row.argpartition(-top_n)[-top_n:]
            for j in sorted(order, key=lambda j: -row[j]):
                s = float(row[j])
                if s < threshold:
                    break
                p = pm_items[j]
                if not _pair_ok(m, p):
                    continue
                if m.market_id not in k_best or s > k_best[m.market_id][1]:
                    k_best[m.market_id] = (p.market_id, s)
                if p.market_id not in pm_best or s > pm_best[p.market_id][1]:
                    pm_best[p.market_id] = (m.market_id, s)
                break  # best surviving candidate for this kalshi market

    out = []
    for k_id, (pm_id, s) in k_best.items():
        best_k_for_pm, _ = pm_best.get(pm_id, (None, -1.0))
        if best_k_for_pm == k_id:
            out.append(Candidate(polymarket_id=pm_id, kalshi_id=k_id, score=s))
    return sorted(out, key=lambda c: -c.score)
