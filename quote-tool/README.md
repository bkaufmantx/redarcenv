# RedArc Quote Tool — v1 (work in progress)

Building the **profiled-waste item-code lookup wizard**: Kristin describes a
waste stream, the tool narrows ~760 item codes to the right one with its all-in
price — instead of scrolling the whole list by hand.

This is **v1 / proof-of-concept**. The goal is to prove the approach on real
data, not to ship perfect data. Coverage and gaps are measured, not hidden.

## The approach

The unlock is `All Profiles.xlsx` — **889 real waste streams, each labeled with
the item code we actually billed and the facility it went to.** That's an answer
key. So instead of hand-encoding all of Zak's routing rules up front, we:

1. **Build a catalog** that joins every source into one queryable file. *(Step 1 — done)*
2. **Rank candidates** for a described waste stream, with price + facility + the
   real profiles that match. *(Step 2 — prototype in `lookup.py`)*
3. **Validate** against the 889 profiles: how often do we land the code that was
   actually billed? Misses pinpoint where Zak's tacit knowledge is needed. *(Step 3)*

## Scripts

| File | What it does |
|---|---|
| `build_catalog.py` | Joins Zak's 5 exports → `data/catalog.json` + `data/profiles.json` + `data/DATA_QUALITY.md` |
| `lookup.py` | Minimal lookup demo — `python3 lookup.py "spent sulfuric acid liquid"` |

## Data sources (Zak's June 11 drop — read-only, never modified)

`All Items` · `Master Item Code Pricing Workbook` (Master List) · `All Profiles`
· `All Vendor Pricing` · the lab-pack skill's CE↔Red Arc code map.

## ⚠️ Confidentiality

The built `data/*.json` contains RedArc's **pricing, margins, and customer/
profile names**, and **this repo is public** (GitHub Pages). Those files are
**gitignored** — only the code and the aggregate quality summary are committed.
Decision pending: make the repo private, or commit a sanitized catalog.

## Build it

```sh
python3 build_catalog.py     # regenerates data/ from the source xlsx
python3 lookup.py "aerosol cans"
```
