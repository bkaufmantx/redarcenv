# RedArc Platform — Estimate Structure Reference
**Pulled:** June 10, 2026 | **Source:** Platform (Zoho Creator) All_Estimates + All_Estimate_Line_Items APIs  
**Purpose:** Pre-call reference for quote walkthrough with Zak. We've already seen a real estimate — we're not going in cold.

---

## How Estimates Work (High Level)

An Estimate in Platform is a two-level object:

1. **Header** — one record with job metadata, pricing totals, boilerplate text, and links to Account + Generator
2. **Line Items** — child records in a separate `All_Estimate_Line_Items` report, each linked back to the header by Estimate ID

The line items are where the actual work lives — each line is one waste stream or service, with its own item code, vendor, cost, and price. A single estimate can have 1–26+ line items.

---

## Header Fields (41 fields)

### Identity & Status
| Field | Type | Notes |
|-------|------|-------|
| `Estimate_Number` | Sequential integer | e.g., "229" — human-readable ID |
| `Title` | Free text | e.g., "Lab Pack Estimate" — appears on the PDF |
| `Subtitle` | Free text | One-liner shown under the title on the PDF |
| `Estimate_Status` | Picklist | "Draft" is the only status seen; likely also Sent, Accepted, Declined |
| `Estimate_Date` | Date | Date the estimate was created |
| `Expiration_Date` | Date | Quote validity — typically 90 days out |
| `Internal_Reference_Number` | Free text | Optional internal ref; often blank |
| `Service_Type` | Lookup | e.g., "Lab Pack" — drives the quote type |
| `Alerts` | Multi-select | e.g., `profiled_required_for_disposal` — flags visible to Zak |

### Client & Site Links
| Field | Type | Notes |
|-------|------|-------|
| `Accounts` | Lookup → Account | The billing company (e.g., "Shield Medical Waste") |
| `Generator` | Lookup → Generator | The physical site (e.g., "Shield Medical Waste of Texas LLC, Keller TX") |
| `Contact` | Lookup → Contact | Primary contact for the quote (e.g., "DENISE STOUTE") |
| `Address` | Address | Override address — blank when using Generator's address |
| `Organization` | Lookup | Always "Red Arc Environmental" — the issuing org |

### Financial Totals (calculated, not entered)
| Field | Notes |
|-------|-------|
| `Subtotal` | Sum of all Extended_Total values before tax |
| `Tax` | Dollar amount of tax — $0.00 on this quote |
| `Estimate_Total` | Subtotal + Tax — the customer-facing number |
| `Estimate_Cost` | Sum of all Extended_Cost values (RedArc's cost) |
| `Estimate_Gross_Profit` | Total - Cost |
| `Estimate_Gross_Margin` | GP / Total — stored as decimal (e.g., 0.4031 = 40.3%) |

### Relationships (often blank on in-progress quotes)
| Field | Notes |
|-------|-------|
| `Opportunity` | Linked opportunity record (CRM concept, usually blank) |
| `Project` | Linked Zoho Projects record |
| `Service_Request` | Linked SR — populated when estimate is converted to a job |
| `Converted_To_SR_Date` | Date the estimate became a service request |
| `Estimate_Owner` | Salesperson — "Zak Wilson" on most quotes |

### PDF / Output Controls (toggle flags)
| Field | Default | Effect |
|-------|---------|--------|
| `Include_Cover_Page` | true | Adds a cover page to the PDF output |
| `Show_Content` | false | Shows/hides the Pre_Line_Item_Content block |
| `Show_Section_Subtotals` | false | Shows subtotals per section in the PDF |
| `Include_Odd_Sized_Container_Table` | false | Adds a table for non-standard containers |
| `Refresh` | true | Internal flag |

### Boilerplate Text Fields
| Field | Notes |
|-------|-------|
| `Pre_Line_Item_Content` | Terms & conditions block printed before line items (see full text below) |
| `Signature_Block_Content` | Signature area — blank on Draft |
| `Left_Footer_Heading` / `Left_Footer` | Two-column footer (left side) |
| `Right_Footer_Heading` / `Right_Footer` | Two-column footer (right side) |
| `Description` | Internal notes field, usually blank |

**Pre_Line_Item_Content (standard boilerplate on every quote):**
> All services are subject to the terms and conditions of the Red Arc Service Agreement, if one is in effect between the parties. In the absence of such an agreement, this quote and any resulting services shall be governed by Red Arc's Standard Terms and Conditions attached hereto and incorporated by reference.
>
> By signing below or otherwise authorizing work to proceed, the customer acknowledges that they have reviewed and agree to be bound by the applicable terms.
>
> Pricing and quantities are based on the best information currently available. Should quantities or waste characteristics differ, pricing is subject to adjustment. All pricing assumes use of Red Arc's approved network of transporters and treatment, storage, and disposal facilities. Disposal rates are contingent upon approval of the corresponding waste stream profiles.

---

## Line Item Fields (20 fields)

Each line item is a separate record in `All_Estimate_Line_Items`, linked to the header.

| Field | Type | Notes |
|-------|------|-------|
| `No` | Integer | Line number — 1, 2, 3… determines sort order on PDF |
| `Estimate` | Lookup → Estimate | Link back to the header (display_value = estimate number) |
| `Description` | Free text | Waste stream description — what appears on the printed quote |
| `Item_Code` | Lookup → Item | Format: `"CODE - Description"` (e.g., `"INC14-AVA - Lab Pack, Incineration, Flammable Liquids"`) |
| `Quantity` | Decimal | Units of service (hours, drums, containers, etc.) |
| `Vendor` | Lookup → Account | TSDF, transporter, or RedArc's own yard — who performs/bills this service |
| `Extended_Cost` | Currency | RedArc's cost for this line (Quantity × unit cost) |
| `Extended_Total` | Currency | Customer price for this line (Quantity × unit price) |
| `Gross_Profit` | Currency | Extended_Total − Extended_Cost |
| `Notes` | Free text | Waste-specific qualifier (e.g., "Flammable/Corrosive", "P-code/PIH") |
| `Section1` | Free text | Section header for grouping lines on the PDF — blank on this quote |
| `Profile` | Lookup → Profile | Linked waste profile (often blank on new quotes) |
| `Specific_Item_Codes` | Free text | Override item codes — rarely used |
| `System_Notes` | Text | Auto-generated system notes |
| `Deleted` | Boolean | Soft-delete flag — `"false"` on active lines |
| `Added_User` | Text | Login who added the line (e.g., `zwilson_redarcenv`, `kgreen_redarcenv`) |
| `Added_Time` | DateTime | Timestamp of line creation |
| `Order` | Text | Secondary sort field — usually blank |
| `Estimate_ID` | Text | Secondary ID field — usually blank (Estimate lookup handles the link) |
| `ID` | Text | Record ID (platform internal) |

### Item Code Naming Convention
Codes follow a `PREFIX##-VENDOR` pattern:
- `LABO` = Labor
- `TRA` = Transport / Freight
- `INC` = Incineration disposal
- `FBL` = Fuel blend disposal
- `HAZ` = Hazardous treatment
- `LF` = Landfill disposal
- `SUP` = Supplies (drums, pails, vermiculite)
- `FEE` = Fees (manifest, admin)
- Suffix `-AVA` = Chemical Reclamation Services (AVA = their code)
- Suffix `-ITA` = Itasca Landfill TX

---

## Live Example: Estimate #229 — Lab Pack, Shield Medical Waste

**Account:** Shield Medical Waste  
**Generator:** Shield Medical Waste of Texas LLC — Keller, TX  
**Contact:** Denise Stoute  
**Date:** June 3, 2026 | **Expires:** Sept 1, 2026  
**Status:** Draft | **Owner:** Zak Wilson  
**Service Type:** Lab Pack

| | |
|--|--|
| **Subtotal / Total** | $16,739.07 |
| **Cost** | $9,991.39 |
| **Gross Profit** | $6,747.68 |
| **Gross Margin** | **40.3%** |
| **Alert** | `profiled_required_for_disposal` |

### Line Items

| # | Description | Item Code | Qty | Vendor | Cost | Price | GP | Notes |
|---|-------------|-----------|-----|--------|-----:|------:|---:|-------|
| 1 | LAB PACK CHEMIST LABOR - HOURLY | LABO04 | 30 hrs | Red Arc Crandall Yard | $1,680.00 | $3,360.00 | $1,680.00 | |
| 2 | LAB PACK CHEMIST LABOR - HOURLY | LABO04 | 30 hrs | Red Arc Crandall Yard | $1,680.00 | $3,360.00 | $1,680.00 | Day 2 labor |
| 3 | LTL FREIGHT - ZONE 1 | TRA20 | 2 | Red Arc Crandall Yard | $430.50 | $775.00 | $344.50 | 1–50 miles |
| 4 | Lab pack, fuels | FBL13-AVA | 1 | CRS | $260.59 | $391.19 | $130.60 | Flammables for fuel blend |
| 5 | Lab Pack, Incineration, Flammable Liquids | INC14-AVA | 1 | CRS | $492.91 | $701.74 | $208.83 | Flammable/Toxic |
| 6 | Lab Pack, Incineration, Flammable Liquids | INC14-AVA | 1 | CRS | $492.91 | $701.74 | $208.83 | Flammable/Corrosive |
| 7 | Lab Pack, Incineration, Flammable Solids (DOT 4.1) — Container Min | INC26-AVA | 1 | CRS | $233.23 | $332.79 | $99.56 | Organic Flammable Solids |
| 8 | Lab Pack, Incineration, Flammable Solids (DOT 4.1) — Container Min | INC26-AVA | 1 | CRS | $233.23 | $332.79 | $99.56 | Inorganic Flammable Solids |
| 9 | Lab Pack, Incineration, Oxidizers | INC15-AVA | 1 | CRS | $431.18 | $610.37 | $179.19 | Regular Compatibility Oxidizers |
| 10 | Lab Pack, Incineration, Oxidizers | INC15-AVA | 1 | CRS | $192.48 | $277.10 | $84.62 | Halogenated Oxidizers |
| 11 | Lab Pack, Incineration, Organic Poisons | INC18-AVA | 1 | CRS | $435.82 | $623.71 | $187.89 | Toxics |
| 12 | Lab Pack, Treatment, Inorganic Acids | HAZ20-AVA | 1 | CRS | $271.91 | $399.66 | $127.75 | Inorganic acids |
| 13 | Lab Pack, Treatment, Inorganic Bases | HAZ21-AVA | 1 | CRS | $271.91 | $399.66 | $127.75 | Inorganic bases |
| 14 | Lab Pack, Incineration, Organic Acids | INC12-AVA | 1 | CRS | $175.44 | $253.81 | $78.37 | Nitric — pack alone for incineration |
| 15 | Lab Pack, Incineration, Organic Acids | INC12-AVA | 1 | CRS | $292.40 | $420.68 | $128.28 | Organic acids / class 3 secondary |
| 16 | Lab Pack, Incineration, Organic Bases | INC13-AVA | 1 | CRS | $339.75 | $485.39 | $145.64 | Organic Bases/Amines/class 3 secondary |
| 17 | Labpack, Reactive (D003), PIH Chemicals, P listed — Container Min | INC35-AVA | 1 | CRS | $233.23 | $332.79 | $99.56 | P-code/PIH or PGI Toxic |
| 18 | Lab Pack, Incineration, Oxidizers (cont.) | INC15-AVA | 1 | CRS | ~$399.66 | ~$399.66 | — | (see Note*) |
| 19 | Class 1 Solid Drums 55/30/15/5 Gal (Landfill) | LF02-ITA | 1 | Itasca Landfill TX | $46.59 | $103.31 | $56.72 | |
| 20 | OPEN TOP POLY DRUM (55) | SUP04 | 1 | Questar Solutions | $69.78 | $119.84 | $50.06 | |
| 21 | OPEN TOP POLY DRUM (30) | SUP05 | 5 | Questar Solutions | $280.75 | $467.90 | $187.15 | |
| 22 | OPEN TOP POLY DRUM (14) | SUP06 | 4 | Questar Solutions | $226.52 | $377.52 | $151.00 | |
| 23 | OPEN TOP POLY PAIL (5) | SUP03 | 5 | Questar Solutions | $57.90 | $97.55 | $39.65 | |
| 24 | VERMICULITE, 4CU. FT. | SUP01 | 6 | Questar Solutions | $179.88 | $327.06 | $147.18 | |
| 25 | E-MANIFEST FEE | FEE02 | 3 | CRS | $77.88 | $90.00 | $12.12 | |
| 26 | Lab Pack, Incineration, Oxidizers | INC15-AVA | 1 | CRS | $431.18 | $610.37 | $179.19 | Hydrogen peroxide |

*CRS = Chemical Reclamation Services, Inc. (vendor code 1922) — primary disposal vendor for this job.

### What this estimate reveals about the quoting workflow

**Three vendor types on one estimate:**
- **Red Arc Crandall Yard** — provides labor (chemist hours) and transport (LTL freight)
- **Chemical Reclamation Services (CRS)** — third-party TSDF; handles incineration, fuel blend, treatment, reactive/P-listed waste
- **Questar Solutions** — supplies (drums, pails, vermiculite)
- **Itasca Landfill TX** — for Class 1 solid waste disposal

**Waste stream logic:** Each line corresponds to a chemical compatibility group. The same item code (e.g., INC14-AVA) can appear multiple times with different Notes to distinguish flammable/toxic vs. flammable/corrosive streams — those go in separate containers and are priced separately even if it's the same disposal route.

**Labor drives the GP:** Lines 1–2 (60 hrs of chemist labor at $112/hr cost, $112/hr markup = 100% margin) contribute $3,360 GP alone — roughly half the total GP on the job.

**Supplies are lower margin:** SUP lines run ~40–72% markup. Landfill is middle (122% markup on the drum fee).

**E-Manifest fee is almost flat:** $77.88 cost → $90.00 billed = ~15% markup. Regulatory cost pass-through.

---

## Other Estimate Types (from sampling recent estimates)

| # | Title | Account | Service Type | Total | Status | Date |
|---|-------|---------|-------------|-------|--------|------|
| 242 | Skyway Circle — Irving T&D | Cura Emergency Services | — | $256.39 | Draft | 06-09-2026 |
| 241 | Paint Waste T&D | D.B.M. Services, LP | — | $973.72 | Draft | 06-09-2026 |
| 240 | Water Testing Kits — Durant, OK T&D | Cura Emergency Services | — | $8,519.29 | Draft | 06-08-2026 |
| 229 | Lab Pack Estimate | Shield Medical Waste | Lab Pack | $16,739.07 | Draft | 06-03-2026 |

"T&D" = Transport & Disposal (simpler job type — fewer line items, no chemist labor). Lab Pack = chemist-intensive, more line items, higher total.

---

## Key Observations for the Quote Tool Build

1. **Item Code is the core unit.** Everything maps to an item code. The quote is essentially: pick waste streams → assign item codes → assign quantities → assign vendor → totals calculate automatically. The item code encodes the disposal route, the compatibility class, and the vendor.

2. **The Notes field distinguishes streams within the same code.** `INC14-AVA` appears twice — once for Flammable/Toxic, once for Flammable/Corrosive. The waste description in Notes is how Zak tracks *what's in each container*, not just the disposal method.

3. **Three vendor categories to manage:** RedArc (labor + transport), TSDF (disposal vendors like CRS, Itasca), and Supplies (Questar). A quote tool needs to know which vendor handles which item code.

4. **~760 item codes exist in Platform** (from the home page count noted earlier). A quote tool needs to search/filter them — not present all 760.

5. **Generator lookup is the entry point.** Generator → Account follows automatically. A quote for a new site requires creating the Generator record first.

6. **Estimates live in Draft until manually converted to a Service Request.** The `Converted_To_SR_Date` field marks that transition. The quote tool only needs to produce a Draft — Zak handles the SR conversion.

7. **Boilerplate is baked in.** The T&C text is the same on every estimate and pulled from the `Pre_Line_Item_Content` field. A Claude-generated quote can embed this verbatim.

8. **No tax on these quotes** ($0.00 Tax field) — either it's always zero or managed outside Platform.

---

*Saved as prep for Phase 3 quote tool build. Reference this before the Zak walkthrough — we've already seen the structure, we just need him to confirm the routing logic and item code selection criteria.*
