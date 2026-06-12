#!/usr/bin/env python3
"""
build_catalog.py — Step 1 of the RedArc quote tool: join Zak's raw exports into
one clean, queryable catalog the lookup wizard can read.

Sources (Zak's June 11 data drop, read-only — never modified):
  - All Items (8).xlsx                     → 761 canonical item codes
  - Red Arc Master Item Code Pricing Workbook.xlsx / "Master List"
                                           → per-container A/B/C tier pricing + routing
  - All Profiles.xlsx                      → 889 real waste streams = the labeled answer key
  - All Vendor Pricing (3).xlsx            → account/profile rate overrides
  - lab-pack-sorter.skill / redarc-ce-code-mapping.csv  → CE process code ↔ Red Arc code

Outputs (data/, gitignored — confidential):
  - catalog.json     one object per item code (description, routing, tier pricing, usage)
  - profiles.json    the 889 labeled examples (waste stream → billed code → facility)
  - DATA_QUALITY.md  match rates + known gaps (this is a v1 — perfect data comes later)

v1 philosophy: useful + honest about gaps, not 100% clean. We measure coverage
rather than pretend it's complete.
"""

import csv
import json
import re
import warnings
from collections import defaultdict
from pathlib import Path

import openpyxl
warnings.filterwarnings("ignore")

SRC = Path("/Users/briankaufman/Desktop/SAR Master Folder/RedArc/Info from Zak June 11")
SKILL_CSV = Path("/tmp/lpskill2/lab-pack-sorter/references/redarc-ce-code-mapping.csv")
OUT = Path(__file__).resolve().parent / "data"
OUT.mkdir(exist_ok=True)


def rows(path, sheet=None, header_row=1):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
    data = list(ws.iter_rows(min_row=header_row, values_only=True))
    header = [str(c).strip() if c is not None else "" for c in data[0]]
    out = []
    for r in data[1:]:
        if any(c is not None for c in r):
            out.append({header[i]: r[i] for i in range(len(header)) if header[i]})
    return out


def s(v):
    return "" if v is None else str(v).strip()


def num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return None


def base_code(code):
    """Strip a -FAC facility suffix: EFW01-AVA -> EFW01. Admin codes unchanged."""
    return re.sub(r"-[A-Z]{2,4}$", "", s(code).upper())


KEYWORD_STOP = {"for", "and", "the", "with", "non", "of", "to", "in", "or", "per"}


def keywords(*texts):
    toks = set()
    for t in texts:
        for w in re.split(r"[^a-z0-9]+", s(t).lower()):
            if len(w) > 2 and w not in KEYWORD_STOP:
                toks.add(w)
    return sorted(toks)


# ── 1. Canonical item codes (All Items) ─────────────────────────────────────
items = rows(SRC / "All Items (8).xlsx")
catalog = {}
for it in items:
    code = s(it.get("Item Code"))
    if not code:
        continue
    catalog[code] = {
        "item_code": code,
        "base_code": base_code(code),
        "description": s(it.get("Item Description")),
        "type": s(it.get("Item Type")),
        "legacy_code": s(it.get("Legacy Item Code")),
        "billing_method": s(it.get("Billing Method")),
        "default_vendor": s(it.get("Default Vendor")),
        "default_customer_price": num(it.get("Default Customer Price")),
        "notes": s(it.get("Item Code Notes")),
        # enriched below:
        "facility": "", "facility_abbrev": "", "treatment_category": "",
        "vendor_process_code": "", "disposal_method": "", "rcra_codes": "",
        "in_house_priority": False,
        "pricing": [],          # per container size: tier A/B/C
        "profile_uses": 0,      # how many real profiles billed this code
        "override_count": 0,    # account/profile-specific negotiated rates
    }

# ── 2. Master List → routing fields + per-container tier pricing ─────────────
ml = rows(SRC / "Red Arc Master Item Code Pricing Workbook.xlsx", "Master List", header_row=3)
ml_by_code = defaultdict(list)
for r in ml:
    ml_by_code[s(r.get("Item Code"))].append(r)

priced = 0
for code, entry in catalog.items():
    rs = ml_by_code.get(code)
    if not rs:
        continue
    priced += 1
    first = rs[0]
    entry["facility"] = s(first.get("Vendor Facility"))
    entry["facility_abbrev"] = s(first.get("Facility Abbrev"))
    entry["treatment_category"] = s(first.get("Treatment Category"))
    entry["vendor_process_code"] = s(first.get("Vendor Process Code"))
    entry["disposal_method"] = s(first.get("Disposal Method"))
    entry["rcra_codes"] = s(first.get("RCRA/Vendor Waste Codes"))
    entry["in_house_priority"] = bool(s(first.get("In-House Priority Flag")) not in ("", "0", "None"))
    for r in rs:
        entry["pricing"].append({
            "container": s(r.get("Billing Method (Container Size)")),
            "vendor_cost": num(r.get("Total Vendor Cost")),
            "tier_a": num(r.get("Price — Tier A (30%)")),
            "tier_b": num(r.get("Price — Tier B (38%)")),
            "tier_c": num(r.get("Price — Tier C (45%)")),
        })

# ── 3. Profiles → the labeled answer key + per-code usage tally ──────────────
profs = rows(SRC / "All Profiles.xlsx")
profiles = []
use_by_base = defaultdict(int)
for p in profs:
    code = s(p.get("Item Code"))
    rec = {
        "profile_no": s(p.get("Profile #")),
        "generator": s(p.get("Generator")),
        "name": s(p.get("Profile Name")),
        "item_code": code,
        "base_code": base_code(code),
        "destination_facility": s(p.get("Destination Facility")),
        "approval_code": s(p.get("Approval Code")),
        "status": s(p.get("Profile Status")),
        "shipping_description": s(p.get("Shipping Description")),
        "hazard_classes": [s(p.get(h)) for h in ("Hazard Class",) if s(p.get(h))],
        "state_waste_codes": s(p.get("State Waste Codes")),
    }
    profiles.append(rec)
    if rec["base_code"]:
        use_by_base[rec["base_code"]] += 1

for entry in catalog.values():
    entry["profile_uses"] = use_by_base.get(entry["base_code"], 0)

# ── 4. Vendor pricing overrides → count per code ────────────────────────────
try:
    vp = rows(SRC / "All Vendor Pricing (3).xlsx")
    ov = defaultdict(int)
    for r in vp:
        ov[s(r.get("Item Code"))] += 1
    for entry in catalog.values():
        entry["override_count"] = ov.get(entry["item_code"], 0) + ov.get(entry["base_code"], 0)
except Exception as e:
    print("  (vendor pricing skipped:", e, ")")

# ── 5. CE process code ↔ Red Arc code cross-reference ───────────────────────
ce_map = []
if SKILL_CSV.exists():
    raw = SKILL_CSV.read_bytes().replace(b"\x00", b"").decode("utf-8-sig", errors="ignore")
    ce_map = [row for row in csv.DictReader(raw.splitlines())]

# ── 6. Search keywords for the wizard ───────────────────────────────────────
for entry in catalog.values():
    entry["keywords"] = keywords(entry["description"], entry["treatment_category"],
                                 entry["rcra_codes"], entry["disposal_method"])

# ── Write outputs ───────────────────────────────────────────────────────────
catalog_list = sorted(catalog.values(), key=lambda e: e["item_code"])
(OUT / "catalog.json").write_text(json.dumps(catalog_list, indent=2))
(OUT / "profiles.json").write_text(json.dumps(profiles, indent=2))
(OUT / "ce_code_map.json").write_text(json.dumps(ce_map, indent=2))

# ── Data-quality report ─────────────────────────────────────────────────────
n = len(catalog_list)
with_price = sum(1 for e in catalog_list if e["pricing"])
with_facility = sum(1 for e in catalog_list if e["facility"])
used = sum(1 for e in catalog_list if e["profile_uses"] > 0)
no_desc = sum(1 for e in catalog_list if not e["description"])
prof_codes = {p["base_code"] for p in profiles if p["base_code"]}
catalog_bases = {e["base_code"] for e in catalog_list}
prof_matched = len(prof_codes & catalog_bases)
disposal = sum(1 for e in catalog_list if e["type"].lower().startswith("disposal"))

report = f"""# RedArc Quote Tool — Catalog Data Quality (v1)

Generated by `build_catalog.py` from Zak's June 11 data drop. This is a **v1
proof-of-concept catalog** — the goal is to prove the lookup/pricing approach,
not to ship perfect data. Coverage is measured below; cleanup comes later.

## Coverage

| Metric | Count | Of total |
|---|---|---|
| Item codes in catalog | {n} | — |
| ↳ Disposal codes | {disposal} | {disposal*100//n}% |
| Codes with A/B/C tier pricing (from Master List) | {with_price} | {with_price*100//n}% |
| Codes with routing facility assigned | {with_facility} | {with_facility*100//n}% |
| Codes actually used by a real profile | {used} | {used*100//n}% |
| Codes missing a description | {no_desc} | {no_desc*100//n}% |

## The answer key

- **{len(profiles)} real waste-stream profiles** loaded as labeled examples
  (waste stream → billed item code → destination facility → approval code).
- **{len(prof_codes)} distinct base codes** appear across those profiles;
  **{prof_matched}** of them match a code in the catalog
  ({prof_matched*100//max(len(prof_codes),1)}% join rate).
- These profiles are the validation set: the wizard's output gets replayed
  against them in Step 3 to measure how often it lands the code that was
  actually billed.

## Known v1 gaps (fix later, not now)

- **Inconsistent descriptions** — codes were generated from vendor rate sheets;
  the same concept appears worded differently ("lab pack" vs "lab packs",
  vendor descriptions left verbatim). The keyword index smooths some of this.
- **Facility suffix vs base code** — profiles carry a base code (`INC14`) +
  a separate destination facility; catalog disposal codes are facility-suffixed
  (`INC14-AVA`). v1 joins on the base code; exact facility-variant resolution is
  a later refinement.
- **Pricing only where Master List has it** — admin/fee/transport codes have a
  default price but no A/B/C container breakout (expected — they aren't tiered).
- **Unused/legacy codes** — codes with 0 profile uses are candidates for the
  cleanup Zak mentioned wanting to do.

## Files

- `catalog.json` — {n} item codes, enriched + keyworded (the wizard's source)
- `profiles.json` — {len(profiles)} labeled examples (the answer key)
- `ce_code_map.json` — {len(ce_map)} Clean Earth ↔ Red Arc code mappings
"""
(OUT / "DATA_QUALITY.md").write_text(report)

print(f"catalog: {n} codes | priced {with_price} | facility {with_facility} | used {used}")
print(f"profiles: {len(profiles)} | base codes {len(prof_codes)} | matched {prof_matched}")
print(f"wrote -> {OUT}/catalog.json, profiles.json, ce_code_map.json, DATA_QUALITY.md")
