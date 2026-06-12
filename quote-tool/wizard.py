#!/usr/bin/env python3
"""
wizard.py — Step 2 of the RedArc quote tool: the profiled-waste recommendation
engine. Given a plain-language waste stream, it recommends a Red Arc item code
with an all-in price, a destination facility, the cheaper alternatives, and the
*why* — grounded in what Zak has actually billed before.

The upgrade over the Step-1 keyword PoC: ranking is driven by the **889 real
profiles** (the answer key), not just catalog keywords. For a described waste we
find the nearest real profiles and recommend the code *they* were billed under —
then layer Zak's routing logic (preferred / backup facility, cost ranking) and
flag low-confidence calls for his review.

This is still v1 — deliberately transparent about its evidence and its doubts.

Usage:  python3 wizard.py "spent sulfuric acid, liquid, corrosive"
        python3 wizard.py --validate        # replay real profiles, score hit-rate
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
CATALOG = json.loads((DATA / "catalog.json").read_text())
PROFILES = json.loads((DATA / "profiles.json").read_text())
RULES = json.loads((DATA / "routing_rules.json").read_text())

BY_CODE = {e["item_code"]: e for e in CATALOG}
BY_BASE = defaultdict(list)
for e in CATALOG:
    BY_BASE[e["base_code"]].append(e)

STOP = {"for", "and", "the", "with", "non", "of", "to", "in", "or", "per", "a", "waste"}


def toks(text):
    return {w for w in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in STOP}


def features(name="", shipping="", state_codes="", extra=""):
    """Parse a waste stream into WEIGHTED features. The structured DOT/state
    signals are far more discriminating than free text, so they're weighted up:
      UN number  ×6  (same UN ≈ same material ≈ same code)
      hazard cls ×3   state code ×2   PG ×1   text token ×1
    """
    f = {}
    def add(k, w):
        f[k] = max(f.get(k, 0), w)
    blob = f"{name} {shipping} {extra}"
    for un in re.findall(r"\bUN\s?(\d{4})\b", blob, re.I):
        add(f"un:{un}", 6)
    ship_clean = re.sub(r"\bUN\s?\d{4}\b", "", shipping, flags=re.I)
    for hz in re.findall(r"(?<![\d.])([1-9](?:\.\d)?)(?![\d.])", ship_clean):
        add(f"hz:{hz}", 3)
    for pg in re.findall(r"\bPG\s?(I{1,3}|[123])\b", blob, re.I):
        add(f"pg:{pg.upper()}", 1)
    for sc in re.split(r"[,\s]+", state_codes or ""):
        sc = sc.strip().lower()
        if sc:
            add(f"sw:{sc}", 2)
    for w in toks(blob):
        if not re.match(r"^un\d", w):
            add(w, 1)
    return f


def wsim(fa, fb):
    """Weighted Jaccard over feature dicts."""
    shared = sum(min(fa[k], fb[k]) for k in fa.keys() & fb.keys())
    if not shared:
        return 0.0
    return shared / (sum(fa.values()) + sum(fb.values()) - shared)


# Precompute features for every profile once.
for _p in PROFILES:
    _p["_feat"] = features(_p["name"], _p["shipping_description"], _p["state_waste_codes"])


def tier_b_55(entry):
    for p in entry["pricing"]:
        if "55" in (p["container"] or "") and p["tier_b"]:
            return p["tier_b"]
    for p in entry["pricing"]:
        if p["tier_b"]:
            return p["tier_b"]
    return entry.get("default_customer_price")


def nearest_profiles(qfeat, k=15, exclude_profile_no=None):
    scored = []
    for p in PROFILES:
        if exclude_profile_no and p["profile_no"] == exclude_profile_no:
            continue
        sim = wsim(qfeat, p["_feat"])
        if sim:
            scored.append((sim, len(qfeat.keys() & p["_feat"].keys()), p))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return scored[:k]


def routing_for(query, candidate):
    """Match Operational Color rules against the query + the candidate's text."""
    hay = (query + " " + candidate.get("description", "") + " " +
           candidate.get("treatment_category", "")).lower()
    hits = []
    for rule in RULES["preferred_by_type"]:
        if any(m in hay for m in rule["match"]):
            hits.append(rule)
    return hits


def recommend(query, state_codes="", exclude_profile_no=None, quiet=False):
    qfeat = features(shipping=query, state_codes=state_codes)
    near = nearest_profiles(qfeat, exclude_profile_no=exclude_profile_no)
    # Vote on the billed base code, weighted by similarity.
    votes = defaultdict(float)
    evidence = defaultdict(list)
    for sim, inter, p in near:
        b = p["base_code"]
        if not b:
            continue
        votes[b] += sim               # weight each neighbor by similarity
        evidence[b].append((sim, p))
    ranked = sorted(votes.items(), key=lambda x: -x[1])

    if not ranked:
        return {"query": query, "confidence": "none", "candidates": [], "near": near}

    total = sum(votes.values())
    top_base, top_vote = ranked[0]
    share = top_vote / total if total else 0
    n_support = len(evidence[top_base])
    conf = "high" if (share >= 0.5 and n_support >= 3) else \
           "medium" if (share >= 0.3 or n_support >= 2) else "low"

    # Facility variants + prices for the winning base code (cost ranking = layer 1).
    variants = sorted(
        [{"code": e["item_code"], "facility": e["facility_abbrev"] or e["facility"][:16],
          "price": tier_b_55(e), "uses": e["profile_uses"]} for e in BY_BASE.get(top_base, [])],
        key=lambda v: (v["price"] is None, v["price"] or 0))

    cand = BY_CODE.get(top_base) or (BY_BASE.get(top_base) or [{}])[0]
    rules = routing_for(query, cand)

    rec = {
        "query": query, "recommended_base": top_base, "confidence": conf,
        "vote_share": round(share, 2), "support": n_support,
        "description": cand.get("description", ""),
        "variants": variants,
        "routing": rules,
        "evidence": [(round(s, 2), p["name"], p["item_code"], p["destination_facility"][:24])
                     for s, p in evidence[top_base][:4]],
        "runners_up": [b for b, _ in ranked[1:4]],
        "top_bases": [b for b, _ in ranked[:5]],
    }
    if not quiet:
        _print(rec)
    return rec


def _print(rec):
    print(f'\n🔎  "{rec["query"]}"\n' + "=" * 70)
    if rec["confidence"] == "none":
        print("  No similar past profiles found — escalate to Zak.")
        return
    flag = {"high": "✓ high", "medium": "~ medium", "low": "⚑ LOW → confirm with Zak"}[rec["confidence"]]
    print(f'  RECOMMEND: {rec["recommended_base"]}  —  {rec["description"][:50]}')
    print(f'  Confidence: {flag}   (real-profile agreement {int(rec["vote_share"]*100)}%, {rec["support"]} matches)')
    if rec["variants"]:
        print("\n  Facility options (all-in B-tier 55G, cheapest first):")
        for v in rec["variants"][:5]:
            ps = f"${v['price']:,.2f}" if v["price"] else "—"
            print(f"      {v['code']:<13} {ps:>11}  [{v['facility']}]  {v['uses']}× billed")
    if rec["routing"]:
        print("\n  Routing notes (Zak's operational logic):")
        for r in rec["routing"]:
            tag = " ⚑verify" if r.get("verify") else (" ⚠no-code" if r.get("no_code") else "")
            print(f"      → prefer {r['preferred']}{tag}: {r['note']}")
    print("\n  Why — real profiles we billed for similar waste:")
    for s, name, code, fac in rec["evidence"]:
        print(f"      {name[:38]:<38} → {code:<8} @ {fac}")
    if rec["runners_up"]:
        print(f"\n  Also considered: {', '.join(rec['runners_up'])}")


def validate(sample=200):
    """Replay real profiles through the engine (leave-one-out): does the
    recommended base code match what was actually billed?"""
    import itertools
    top1 = top3 = top5 = total = 0
    by_conf = defaultdict(lambda: [0, 0])
    step = max(1, len(PROFILES) // sample)
    for p in itertools.islice(PROFILES, 0, None, step):
        q = p["name"] + " " + p["shipping_description"]
        if not p["base_code"] or not toks(q):
            continue
        rec = recommend(q, state_codes=p["state_waste_codes"],
                        exclude_profile_no=p["profile_no"], quiet=True)
        if rec["confidence"] == "none":
            continue
        total += 1
        bases = rec["top_bases"]
        t1 = rec["recommended_base"] == p["base_code"]
        top1 += t1
        top3 += p["base_code"] in bases[:3]
        top5 += p["base_code"] in bases[:5]
        by_conf[rec["confidence"]][0] += t1
        by_conf[rec["confidence"]][1] += 1
    pct = lambda h: f"{h*100//max(total,1)}%"
    print("\nVALIDATION — leave-one-out replay of real profiles (the billed code is the truth)")
    print("=" * 72)
    print(f"  Recommended code is the actually-billed code:")
    print(f"    Top-1 (single best guess):     {top1}/{total} = {pct(top1)}")
    print(f"    Top-3 (in the shortlist):      {top3}/{total} = {pct(top3)}   ← the 'narrow it down' metric")
    print(f"    Top-5 (in the shortlist):      {top5}/{total} = {pct(top5)}")
    print(f"\n  Top-1 by confidence (the auto-suggest tier):")
    for c in ("high", "medium", "low"):
        h, t = by_conf[c]
        if t:
            print(f"    {c:<7}: {h}/{t} = {h*100//t}%   ({t*100//total}% of all cases)")
    print("\n  Read: 'narrow 760 codes to a shortlist of 3' is the actual job — that's the")
    print("  top-3 number. High-confidence top-1 calls are the ones safe to auto-fill;")
    print("  the rest still hand Kristin a short list instead of the whole catalog.")


if __name__ == "__main__":
    if "--validate" in sys.argv:
        validate()
    elif len(sys.argv) > 1:
        recommend(" ".join(a for a in sys.argv[1:] if not a.startswith("--")))
    else:
        for q in ["spent sulfuric acid liquid corrosive",
                  "aerosol paint cans",
                  "flammable solvent mineral spirits acetone",
                  "non-hazardous solidification sludge"]:
            recommend(q)
