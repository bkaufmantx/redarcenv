#!/usr/bin/env python3
"""
build_demo_data.py — produce a DE-IDENTIFIED dataset for the public web demo.

The dashboard is public. The full catalog has customer/generator names and exact
pricing — confidential. This strips both:
  - generator/customer names  → removed entirely
  - exact $ prices            → replaced with relative bands ($ / $$ / $$$) per
                                facility, so "cheapest route" still shows but real
                                rates don't leak

Item codes, descriptions, routing logic, hazard matching, and the de-identified
profile evidence remain — that's the intelligence we want Zak to see.

Output: demo/demo_data.json  (safe to publish)
"""

import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CATALOG = json.loads((HERE / "data" / "catalog.json").read_text())
PROFILES = json.loads((HERE / "data" / "profiles.json").read_text())
RULES = json.loads((HERE / "data" / "routing_rules.json").read_text())
OUT = HERE / "demo"
OUT.mkdir(exist_ok=True)


def tier_b_55(e):
    for p in e["pricing"]:
        if "55" in (p["container"] or "") and p["tier_b"]:
            return p["tier_b"]
    for p in e["pricing"]:
        if p["tier_b"]:
            return p["tier_b"]
    return e.get("default_customer_price")


# Relative price band per facility variant, within each base code.
by_base = defaultdict(list)
for e in CATALOG:
    by_base[e["base_code"]].append(e)
band = {}
for base, variants in by_base.items():
    priced = sorted([(tier_b_55(v), v["item_code"]) for v in variants if tier_b_55(v)])
    for rank, (_, code) in enumerate(priced):
        band[code] = "$" * (1 + min(rank, 2))   # cheapest = $, then $$, $$$

demo_catalog = [{
    "item_code": e["item_code"],
    "base_code": e["base_code"],
    "description": e["description"],
    "type": e["type"],
    "facility": e["facility_abbrev"],
    "treatment_category": e["treatment_category"],
    "keywords": e["keywords"],
    "price_band": band.get(e["item_code"], ""),
    "profile_uses": e["profile_uses"],
} for e in CATALOG]

# Profiles: drop the generator (customer). Keep de-identified waste evidence.
demo_profiles = [{
    "name": p["name"],
    "base_code": p["base_code"],
    "item_code": p["item_code"],
    "destination_facility": p["destination_facility"],
    "shipping_description": p["shipping_description"],
    "state_waste_codes": p["state_waste_codes"],
} for p in PROFILES if p["base_code"]]

payload = {
    "note": "De-identified demo data — no customer names, prices shown as relative bands.",
    "catalog": demo_catalog,
    "profiles": demo_profiles,
    "routing_rules": RULES["preferred_by_type"],
}
(OUT / "demo_data.json").write_text(json.dumps(payload, separators=(",", ":")))
size_kb = (OUT / "demo_data.json").stat().st_size // 1024
print(f"wrote demo/demo_data.json — {len(demo_catalog)} codes, {len(demo_profiles)} profiles, {size_kb} KB")
print("  ✓ generator/customer names removed   ✓ exact prices → relative bands")
