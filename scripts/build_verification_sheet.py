"""Verification pipeline: automated checks per candidate pair.

For every candidate (score >= 85 or both priced), pull both markets' raw
records and compute:
- pm_prop: the Polymarket proposition leg's outcome name plus question
- k_subject: Kalshi subtitle (or title)
- orientation: 'same' when the PM proposition subject appears in the K
  subject side, 'inverse' when the OTHER PM outcome appears instead,
  'na' for Yes/No markets, 'unclear' otherwise
- rules_head: first 220 chars of each side's resolution text for reading
Outputs one JSON per pair to review_pairs.jsonl and a per-class summary.
"""
import sqlite3, json, csv, collections, sys, re

conn = sqlite3.connect("data/marketlens.sqlite")
rows = list(csv.DictReader(open("reports/match_candidates.csv")))
cand = [r for r in rows if float(r["score"]) >= 85 or r["both_have_prices"] == "1"]

pm_raw = {}
k_raw = {}
for mid, raw in conn.execute("SELECT market_id, raw_json FROM markets WHERE platform='polymarket'"):
    pm_raw[mid] = raw
for mid, raw in conn.execute("SELECT market_id, raw_json FROM markets WHERE platform='kalshi'"):
    k_raw[mid] = raw

def norm(s):
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).split()

def load_json_field(d, key):
    v = d.get(key)
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v) if v else []
        return out if isinstance(out, list) else []
    except Exception:
        return []

out = []
for r in cand:
    pm = json.loads(pm_raw[r["pm_id"]])
    km = json.loads(k_raw[r["kalshi_id"]])
    outcomes = load_json_field(pm, "outcomes")
    leg = 0
    for i, o in enumerate(outcomes):
        if str(o).strip().lower() == "yes":
            leg = i
    pm_is_yesno = [str(o).lower() for o in outcomes] in (["yes", "no"], ["no", "yes"])
    k_subject = km.get("yes_sub_title") or km.get("title") or ""
    orientation = "na"
    if not pm_is_yesno and len(outcomes) == 2:
        prop_tokens = set(norm(outcomes[leg]))
        other_tokens = set(norm(outcomes[1 - leg]))
        subj_tokens = set(norm(k_subject)) | set(norm(km.get("title")))
        prop_hit = len(prop_tokens & subj_tokens) / max(1, len(prop_tokens))
        other_hit = len(other_tokens & subj_tokens) / max(1, len(other_tokens))
        if prop_hit >= 0.6 and other_hit < prop_hit:
            orientation = "same"
        elif other_hit >= 0.6 and prop_hit < other_hit:
            orientation = "inverse"
        else:
            orientation = "unclear"
    out.append({
        "pm_id": r["pm_id"], "kalshi_id": r["kalshi_id"], "score": r["score"],
        "series": r["kalshi_id"].split("-")[0],
        "category": r["kalshi_category"],
        "pm_title": r["pm_title"], "pm_outcomes": outcomes, "pm_leg": leg,
        "k_title": km.get("title"), "k_sub": km.get("yes_sub_title"),
        "orientation": orientation,
        "pm_desc": (pm.get("description") or "")[:220],
        "k_rules": (km.get("rules_primary") or "")[:220],
        "both_priced": r["both_have_prices"],
    })

with open(sys.argv[1], "w") as f:
    for o in out:
        f.write(json.dumps(o) + "\n")

summary = collections.Counter((o["series"], o["orientation"]) for o in out)
per_series = collections.defaultdict(collections.Counter)
for o in out:
    per_series[o["series"]][o["orientation"]] += 1
big = sorted(per_series.items(), key=lambda kv: -sum(kv[1].values()))
for s, c in big[:25]:
    print(s, dict(c), "total", sum(c.values()))
print("TOTAL", len(out))

