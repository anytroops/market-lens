"""Apply verification decisions to match candidates.

Codes: 1 (same proposition), inv (same, inverted leg), br (same event,
differing resolution criteria: divergence yes, backtest no), 0 (different
propositions), '' (unreviewed, only for sub-85 scores).

Decisions were made by reading both markets' titles, descriptions, and
rules text per template class (samples) plus every pair outside the big
template classes individually. A universal SUBJECT CHECK rejects any
accepted pair whose Kalshi subtitle tokens are not covered by the
Polymarket title (catches same-template different-person pairs).
"""
import sqlite3, json, csv, re, sys, collections, unicodedata

from rapidfuzz import fuzz

# Class-level decisions: series ticker -> code
ACCEPT = set("""KXWCGOAL KXWCAST KXPGATOP5 KXPGATOP10 KXPGATOP20 KXPGATOUR
KXEUROVISIONRANK KXEUROVISIONTELEV KXFOMEN KXFOWOMEN KXSURVIVOR
KXCHESSNORWAY KXIPL KXNCAABASEBALL KXNBAMVP KXNHLADAMS KXNHLNORRIS
KXNHLCALDER KXNHLHART KXNHLVEZINA KXNBACOY KXTOPSONG KXTOPALBUM
KXBBCHARTPOSITIONSONG KXMETGALAFITS KXFARRERBYELECTION KXDAEGUMAYOR
KXNEWARKMAYOR KXSEOULMAYOR KXCOPPAITALIA KXFACUP KXCOUPEDEFRANCE
KXSERIEATOP4 KXBUNDESLIGATOP4 KXLIGAMX KXDFBPOKAL KXIIHF KXVALORANT
KXCS2 KXCS2QUALIFIERS KXEPLRELEGATION KXLALIGARELEGATION
KXBUNDESLIGARELEGATION KXSERIEARELEGATION KXLEMANS24H KXINDYCARRACE
KXNEXTHUNGARYPM KXVANCEPAKISTAN KXKNESSET KXFABLERESTORE KXSENATEREC
KXDASHORDERS KXPLTR KXPSKY KXMLBALLSTAR KXNBADRAFT1 KXNHLDRAFTPICK
KXWCROUND KXSPACEXCOUNT KXPERUPRESMATCHUP KXCA04PRIMARY KXCA22PRIMARY
KXLARSENR1 KXATTENDTRUMPCHINA KXNHLSERIESSCORE KXEPLTOTAL
KXBUNDESLIGATOTAL KXEPLBTTS KXMLSBTTS KXSERIEABTTS KXLALIGABTTS
KXLIGUE1BTTS KXBUNDESLIGABTTS KXCFLGAME KXISLGAME KXLNBELITEGAME
KXPREMCHAMP KXLOLMAP KXVALORANTMAP KXCS2MAP KXATPSETWINNER
KXWTASETWINNER KXWCGROUPWIN KXTRUMPCHINA KXVANCEMENTION
KXMRBEASTMENTION KXLAMAYOR1ROUND KXNBAFINMVP KXNBAWFINMVP KXNBAEFINMVP
KXUCLBTTS KXUECLBTTS KXUELBTTS""".split())

# Nominee <-> nominee election templates (identical criteria both sides).
NOMINEE_RE = re.compile(r"^KX(NY\d+D|SENATE\w+|KXSENATE\w+|[A-Z]{2}\d*PRIMARY|PA\d+D|PA07D|CO\d+[DR]|NE2[DR]|UT1D|KY4R|ME02D|IA02R|MD06D|TX33D|TX18D|SC01R|NJ07D|OH9R|MTPRIMARY|NY\d+D)$")

REJECT = set("""KXEUROVISION KXEUROVISIONJURY KXWCMOV KXWCSTAGEOFELIM
KXWCBTTS KXWCGROUPBOTTOM KXUFCMOV KXUFCVICROUND KXUFCMOF KXUFCDISTANCE
KXPERUPRES KXMAYORLA KXWCGSGOALS KXWCGOALCOUNT KXWCGOALCOMBO
KXWCGOALSALLOWED KXWCTEAM1STGOAL KXTEAMSINNCAABBWS KXTEAMSINNBAWF
KXNHLSERIESGAMES KXNBASERIESGAMES KXNHLTOTAL KXPGAMAKECUT KXWTAADVANCE
KXATPADVANCE KXARBROATHBY KXABERDEENSOUTHBY KXMAKERFIELDBY KXGREENMAYOR
KXIPLGAME KXMENWORLDCUP KXCOLOMBIAPRES KXCOLOMBIAPRESR1 KXCPICORE
KXNHLPLAYOFFGOALS KXLEADERUCLGOALS KXUCL KXWCFTTS KXWCFURTHESTADVANCING
KXVOTEPRIMARY KXLAMAYORADVANCE KXCBRATEHIKE KXDOTA2GAME KXATPGSPREAD
KXNBASERIES3PMLEADER KXLLM1 KXNBA2D KXATPGRANDSLAMFIELD KXFEATUREDRAKE
KXTRYFIREPOWELL KXAGNOMCOD KXGOVGANOMR KXGOVOKNOMR KXNVPRIMARY
KXARGPREMDIVBTTS KXPERUPRES1R""".split())

# KXFABLERESTORE is the project's cleanest demonstrated basis-risk case:
# Polymarket resolves on the restoration itself, Kalshi on whether a
# Source Agency REPORTS it. The pair actually resolved YES on one venue
# and NO on the other, which is basis risk realized rather than theorized.
BASIS_RISK = set("""KXFABLERESTORE KXRT KXGOVNMNOMR KXGOVNMNOMD KXGOVSCNOMD KXGOVSCNOMR
KXGOVALNOMR KXGOVALNOMD KXGOVORNOMR KXGOVOHNOMR KXGOVMDNOMR KXGOVNENOMR
KXGOVGANOMD KXAGNOMTXR KXVOTEFEDCHAIR KXTRAVISKELCEWEDDING
KXSCOTPARLIAMENT KXWALESPARLIAMENT""".split())

# KXNBA is Finals winner (verified 1); KXPERUPRES1R rejected because
# mutual-best matched wrong finishing places.
ACCEPT.add("KXNBA")

WEATHER_RE = re.compile(r"^KX(HIGH|LOW|MIN|MAX)")

STOP = set("the a an of in at for to and or vs will be win wins won by on".split())
# Club-name boilerplate: never distinctive enough to identify a fixture.
GENERIC_CLUB = set(
    "fc sc cf ac afc cd club city united town athletic real deportivo".split())
# Kalshi fixture rules read "If X and Y both score goals in the X vs Y ...".
TEAMS_RE = re.compile(r"^If (.+?) and (.+?) both score", re.I)
NAME_MATCH = 85  # rapidfuzz ratio treated as the same word


def strip_accents(s):
    """Mbappe and Mbappé must tokenize identically.

    Without this the punctuation stripper turned accented letters into
    word breaks, so real pairs failed a strict name check while the
    loose check that compensated let wrong people through.
    """
    return "".join(c for c in unicodedata.normalize("NFKD", s or "")
                   if not unicodedata.combining(c))


def norm_tokens(s):
    cleaned = re.sub(r"[^a-z0-9 ]+", " ", strip_accents(s).lower())
    return [t for t in cleaned.split() if t not in STOP]


def _fuzzy_in(token, haystack_tokens):
    return any(fuzz.ratio(token, h) >= NAME_MATCH for h in haystack_tokens)


def subject_ok(k_sub, pm_title, pm_outcomes):
    """The Kalshi subtitle's entity must really be the Polymarket subject.

    Requires the LAST substantive token (the surname for people, the
    distinguishing word for teams and titles) to appear, not just half
    the tokens. The loose 50% rule matched "Austin Eckroat" to "Austin
    Smotherman" on the shared first name, which the outcome audit caught.
    """
    toks = [t for t in norm_tokens(k_sub) if len(t) >= 3 and not t.isdigit()]
    if not toks:
        return True  # generic subtitle: the fixture check handles these
    hay = set(norm_tokens(pm_title)) | set(
        t for o in pm_outcomes for t in norm_tokens(str(o)))
    if not _fuzzy_in(toks[-1], hay):
        return False
    hits = sum(1 for t in toks if _fuzzy_in(t, hay))
    return hits / len(toks) >= 0.5


def fixture_ok(pm_title, pm_desc, k_rules):
    """Generic-title fixture markets must name the same two teams.

    Parses both team names out of the Kalshi rules sentence and requires
    each to share a distinctive token with the Polymarket side. The old
    version counted any long word, so boilerplate ("score", "goals",
    "match") satisfied it and Bundesliga fixtures matched Chinese Super
    League ones; seven such pairs were caught by the outcome audit.
    """
    m = TEAMS_RE.match((k_rules or "").strip())
    if not m:
        return True
    hay = set(norm_tokens(pm_title)) | set(norm_tokens(pm_desc))
    for team in m.groups():
        tt = [t for t in norm_tokens(team)
              if len(t) >= 3 and t not in GENERIC_CLUB]
        if tt and not any(_fuzzy_in(t, hay) for t in tt):
            return False
    return True

# Sport fingerprints. Polymarket reuses generic titles like "Will England
# win?" across sports and puts the real context only in the description,
# so a title-level match can silently cross sports: the outcome audit
# caught a cricket market matched to a football World Cup group.
SPORT_WORDS = {
    "cricket": ("cricket", "test series", "odi", "t20", "wickets"),
    "soccer": ("soccer", "fifa", "premier league", "la liga", "bundesliga",
               "serie a", "ligue 1", "mls", "uefa", "goals"),
    "basketball": ("basketball", "nba", "euroleague"),
    "hockey": ("hockey", "nhl", "iihf"),
    "baseball": ("baseball", "mlb", "innings"),
    "tennis": ("tennis", "atp", "wta", "set 1", "grand slam"),
    "golf": ("golf", "pga", "tee", "the cut"),
    "football": ("nfl", "touchdown", "quarterback"),
}


def sports_conflict(pm_text, k_text):
    """True when the two sides clearly describe different sports."""
    def sports_in(text):
        t = strip_accents(text or "").lower()
        return {s for s, words in SPORT_WORDS.items() if any(w in t for w in words)}
    a, b = sports_in(pm_text), sports_in(k_text)
    return bool(a) and bool(b) and not (a & b)


FIXTURE_CLASSES = {"KXEPLBTTS", "KXMLSBTTS", "KXSERIEABTTS", "KXLALIGABTTS",
                   "KXLIGUE1BTTS", "KXBUNDESLIGABTTS", "KXUCLBTTS",
                   "KXUECLBTTS", "KXUELBTTS", "KXEPLTOTAL",
                   "KXBUNDESLIGATOTAL", "KXWCGROUPWIN"}

ANIME_RE = re.compile(r"^KXANIME")

# Individually-decided overrides by (pm_id, kalshi_id) are unnecessary:
# the class rules plus checks reproduce every individual verdict except
# these explicit ones.
PAIR_OVERRIDES = {}

def orient_from_subtitle(outcomes, leg, k_sub):
    """same/inverse/unclear from the Kalshi subtitle vs the PM leg outcome."""
    if [str(o).lower() for o in outcomes] in (["yes", "no"], ["no", "yes"]):
        return "na"
    if len(outcomes) != 2:
        return "unclear"
    prop = set(norm_tokens(str(outcomes[leg])))
    other = set(norm_tokens(str(outcomes[1 - leg])))
    subt = set(norm_tokens(k_sub))
    ph = len(prop & subt) / max(1, len(prop))
    oh = len(other & subt) / max(1, len(other))
    if ph >= 0.6 and oh < ph:
        return "same"
    if oh >= 0.6 and ph < oh:
        return "inverse"
    return "unclear"


def decide(p):
    series, sub = p["series"], p["k_sub"]
    pm_title, pm_desc = p["pm_title"], p["pm_desc"]
    outcomes = p["pm_outcomes"]
    orient = orient_from_subtitle(outcomes, p["pm_leg"], sub)

    code = None
    # Metric-word checks added 2026-07-17 after price data exposed two
    # verification misses: a PM "2+ shots" market had matched the assists
    # series, and the SpaceX pair title said June while Kalshi's series is
    # the full-year count (48 point persistent spread confirmed different
    # propositions; title/rules conflict makes resolution ambiguous).
    if series == "KXWCGOAL" and "goal" not in pm_title.lower():
        return "0", ""
    if series == "KXWCAST" and "assist" not in pm_title.lower():
        return "0", ""
    if series == "KXSPACEXCOUNT":
        return "0", ""
    if series == "KXWCUSAOPPONENT":
        # PM "USA reach R16" vs K "USA not make R16" is a valid inverse;
        # every other pair in the series is reach-vs-matchup, rejected.
        if "usa reach" in pm_title.lower() and "not make" in (p["k_title"] or "").lower():
            return "inv", "inverse"
        return "0", ""
    if series == "KXLAMAYOR1R":
        if "finish second" in pm_title.lower():
            return "0", ""
        if not subject_ok(sub, pm_title, outcomes):
            return "0", ""
        return "1", "same"
    if series == "KXATTENDUFC250":
        if not subject_ok(sub, pm_title, outcomes):
            return "0", ""
        return "1", "same"
    if series in REJECT:
        return "0", ""
    if series in BASIS_RISK:
        code = "br"
    elif ANIME_RE.match(series):
        # Award CATEGORY phrase from the K title must appear in PM title.
        m = re.search(r"award for (.+?)\??$", (p["k_title"] or "").lower())
        cat = m.group(1) if m else ""
        if cat and all(t in norm_tokens(pm_title) for t in norm_tokens(cat)):
            code = "1"
        else:
            return "0", ""
    elif WEATHER_RE.match(series):
        code = "1"  # numbers, min/max, city all enforced by matcher guards
    elif series in ACCEPT or NOMINEE_RE.match(series):
        code = "1"
    else:
        return "", ""  # unreviewed class

    if series == "KXTRUMPCHINA" and "visit" not in pm_title.lower():
        return "0", ""
    if series == "KXNBAWFINMVP" and "western" not in pm_title.lower():
        return "0", ""
    if series == "KXNBAEFINMVP" and "eastern" not in pm_title.lower():
        return "0", ""
    if series == "KXNBAFINMVP" and "finals mvp" not in pm_title.lower():
        return "0", ""
    if not subject_ok(sub, pm_title, outcomes):
        return "0", ""
    if series in FIXTURE_CLASSES and not fixture_ok(pm_title, pm_desc, p["k_rules"]):
        return "0", ""
    if sports_conflict(f"{pm_title} {pm_desc}", f"{p['k_title']} {p['k_rules']}"):
        return "0", ""

    if code == "1" and orient == "inverse":
        return "inv", "inverse"
    if code == "1" and orient == "unclear":
        return "", ""  # cannot orient: leave unverified
    return code, ("same" if orient in ("same", "na") else orient)

pairs = [json.loads(l) for l in open(sys.argv[1])]
stats = collections.Counter()
codes = {}
for p in pairs:
    code, orient = decide(p)
    codes[(p["pm_id"], p["kalshi_id"])] = (code, orient)
    stats[code or "(blank)"] += 1
print("decision counts:", dict(stats))

# series-level summary of unreviewed classes for transparency
blank_series = collections.Counter(
    p["series"] for p in pairs
    if codes[(p["pm_id"], p["kalshi_id"])][0] == "")
print("unreviewed/unoriented series:", dict(blank_series.most_common(12)))

# 1. Write codes into the CSV
rows = list(csv.DictReader(open("reports/match_candidates.csv")))
fields = list(rows[0].keys())
if "verified_by" not in fields:
    fields.append("verified_by")
n_set = 0
for r in rows:
    key = (r["pm_id"], r["kalshi_id"])
    if key in codes and codes[key][0]:
        r["verified"] = codes[key][0]
        r["verified_by"] = "claude-2026-07-10"
        n_set += 1
    else:
        r.setdefault("verified_by", "")
with open("reports/match_candidates.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader(); w.writerows(rows)
print(f"CSV: {n_set} rows coded")

# 2. Update matches table
conn = sqlite3.connect("data/marketlens.sqlite")
cols = [r[1] for r in conn.execute("PRAGMA table_info(matches)")]
if "orientation" not in cols:
    conn.execute("ALTER TABLE matches ADD COLUMN orientation TEXT")
if "basis_risk" not in cols:
    conn.execute("ALTER TABLE matches ADD COLUMN basis_risk INTEGER DEFAULT 0")
n_ver = 0
for (pm_id, k_id), (code, orient) in codes.items():
    if code in ("1", "inv", "br"):
        conn.execute(
            """UPDATE matches SET human_verified = 1, orientation = ?,
               basis_risk = ? WHERE polymarket_id = ? AND kalshi_id = ?""",
            ("inverse" if code == "inv" else "same",
             1 if code == "br" else 0, pm_id, k_id))
        n_ver += 1
conn.commit()
print(f"matches table: {n_ver} rows marked verified")
print("verified in db:", conn.execute(
    "SELECT COUNT(*), SUM(basis_risk), SUM(orientation='inverse') FROM matches WHERE human_verified=1").fetchone())
