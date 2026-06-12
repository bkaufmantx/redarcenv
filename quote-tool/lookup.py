#!/usr/bin/env python3
"""
lookup.py — a minimal proof-of-concept of the profiled-waste lookup wizard.

Given a plain-language description of a waste stream, it (1) ranks candidate
Red Arc item codes from the catalog and (2) shows the real past profiles that
match — the "this is what we actually billed for similar waste" evidence.

This is a v1 teaser of Step 2, run against the Step 1 catalog. Scoring is simple
keyword overlap — deliberately dumb, to prove the data supports the workflow
before we add the real routing logic (cost/criteria/backup-facility layers).

Usage:  python3 lookup.py "spent sulfuric acid, liquid, corrosive"
"""

import json
import re
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
CATALOG = json.loads((DATA / "catalog.json").read_text())
PROFILES = json.loads((DATA / "profiles.json").read_text())

STOP = {"for", "and", "the", "with", "non", "of", "to", "in", "or", "per", "a"}


def toks(text):
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOP}


def tier_b_55(entry):
    """Pull the standard default rate: B-tier, 55-gallon (or any B price)."""
    for p in entry["pricing"]:
        if "55" in (p["container"] or "") and p["tier_b"]:
            return p["tier_b"]
    for p in entry["pricing"]:
        if p["tier_b"]:
            return p["tier_b"]
    return entry.get("default_customer_price")


def search(query, n=6):
    q = toks(query)
    scored = []
    for e in CATALOG:
        kw = set(e["keywords"])
        overlap = len(q & kw)
        if not overlap:
            continue
        score = overlap
        if e["type"].lower().startswith("disposal"):
            score += 1                       # we want disposal codes, not admin
        if e["profile_uses"] > 0:
            score += min(e["profile_uses"], 3) * 0.5   # real-world corroboration
        scored.append((score, e))
    scored.sort(key=lambda x: (-x[0], -x[1]["profile_uses"]))
    return [e for _, e in scored[:n]]


def matching_profiles(query, n=4):
    q = toks(query)
    scored = []
    for p in PROFILES:
        overlap = len(q & toks(p["name"] + " " + p["shipping_description"]))
        if overlap:
            scored.append((overlap, p))
    scored.sort(key=lambda x: -x[0])
    return [p for _, p in scored[:n]]


def run(query):
    print(f'\n🔎  "{query}"\n' + "=" * 64)
    print("\nCANDIDATE ITEM CODES (catalog):")
    for e in search(query):
        price = tier_b_55(e)
        price_s = f"${price:,.2f}" if price else "—"
        fac = e["facility_abbrev"] or e["facility"][:18] or "—"
        used = f"{e['profile_uses']}× used" if e["profile_uses"] else "unused"
        print(f"  {e['item_code']:<12} {e['description'][:42]:<42} {price_s:>11}  [{fac}]  {used}")

    print("\nREAL PROFILES THAT LOOK SIMILAR (the answer key):")
    for p in matching_profiles(query):
        print(f"  {p['name'][:40]:<40} → {p['item_code']:<8} @ {p['destination_facility'][:24]}  (appr {p['approval_code']})")


if __name__ == "__main__":
    queries = [" ".join(sys.argv[1:])] if len(sys.argv) > 1 else [
        "spent sulfuric acid liquid corrosive",
        "flammable solvent for incineration",
        "aerosol cans",
    ]
    for query in queries:
        run(query)
