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


def tier_b_55(entry):
    for p in entry["pricing"]:
        if "55" in (p["container"] or "") and p["tier_b"]:
            return p["tier_b"]
    for p in entry["pricing"]:
        if p["tier_b"]:
            return p["tier_b"]
    return entry.get("default_customer_price")


def nearest_profiles(query, k=15, exclude_profile_no=None):
    q = toks(query)
    scored = []
    for p in PROFILES:
        if exclude_profile_no and p["profile_no"] == exclude_profile_no:
            continue
        pt = toks(p["name"] + " " + p["shipping_description"])
        inter = len(q & pt)
        if inter:
            sim = inter / (len(q | pt) or 1)          # Jaccard
            scored.append((sim, inter, p))
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


def recommend(query, exclude_profile_no=None, quiet=False):
    near = nearest_profiles(query, exclude_profile_no=exclude_profile_no)
    # Vote on the billed base code, weighted by similarity.
    votes = defaultdict(float)
    evidence = defaultdict(list)
    for sim, inter, p in near:
        b = p["base_code"]
        if not b:
            continue
        votes[b] += sim
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
    hits = total = 0
    by_conf = defaultdict(lambda: [0, 0])
    step = max(1, len(PROFILES) // sample)
    for p in itertools.islice(PROFILES, 0, None, step):
        q = p["name"] + " " + p["shipping_description"]
        if not p["base_code"] or not toks(q):
            continue
        rec = recommend(q, exclude_profile_no=p["profile_no"], quiet=True)
        if rec["confidence"] == "none":
            continue
        total += 1
        ok = rec["recommended_base"] == p["base_code"]
        hits += ok
        by_conf[rec["confidence"]][0] += ok
        by_conf[rec["confidence"]][1] += 1
    print("\nVALIDATION — leave-one-out replay of real profiles")
    print("=" * 70)
    print(f"  Overall: {hits}/{total} recommended the actually-billed base code = {hits*100//max(total,1)}%")
    for c in ("high", "medium", "low"):
        h, t = by_conf[c]
        if t:
            print(f"    {c:<7}: {h}/{t} = {h*100//t}%   ({t*100//total}% of cases)")
    print("\n  Read: high-confidence calls are the auto-fill candidates; low-confidence")
    print("  ones are exactly where Zak's review (the tribal approvals knowledge) is needed.")


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
