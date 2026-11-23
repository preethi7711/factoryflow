# Project spec: FactoryFlow

Source of truth for **what** we build. The original brief is [PROBLEM.md](PROBLEM.md) (never edited).
This file restates it as testable requirements plus our assumptions.

## 1. Goal

Each transaction is entered once, at its source, and then flows into stock, production, costing and accounts.
**Definition of done:** the section 5 benchmark runs end to end as an automated test (`pytest -m benchmark`)
and in the demo video.

## 2. Roles and access

| Role | Can | Cannot |
| --- | --- | --- |
| salesman | create and read **own** orders, read customers, products and price list | see costs, other salesmen's orders, invoices of others |
| admin | approve/reject/edit orders, raise and cancel invoices, dispatch, record payments, manage masters | edit the stock ledger directly |
| production | record purchases/receipts, production runs, issues, output, wastage, adjustments | see sales, invoices, payments |
| auditor | read and export all reports | write anything |
| owner | read dashboard and all reports | (read-only in prototype) |

**Seeded test logins** (dev/demo only; password = `SEED_DEMO_PASSWORD` from `.env`; listed in the README):

| Username | Role | Notes |
|---|---|---|
| `salesman_a` | salesman | owns Retailer A (TN) |
| `salesman_b` | salesman | owns Distributor B (KA) |
| `admin` | admin | billing desk |
| `production` | production | floor supervisor |
| `accountant` | auditor | read-only reports |
| `owner` | owner | dashboard |

## 3. Requirements by tier

IDs are referenced from tests and commits.

### Must have (gate: nothing else until the benchmark passes)
- **M1** Login with roles salesman, admin, production (plus auditor, owner). Deny by default.
- **M2** Masters: product (+pack size, HSN, GST rate, price), customer (+GSTIN, state), item (raw and packaging, base unit), BOM.
- **M3** Mobile-friendly order entry. Approval queue with a stock-cover check.
- **M4** GST tax invoice as PDF: GSTIN, HSN, taxable value, CGST+SGST or IGST by place of supply, FY numbering.
- **M5** Production run posts raw/packaging issues (−) and finished-goods output (+) to the ledger automatically.
- **M6** Planned vs actual consumption and yield, with variance %.
- **M7** Stock summary and stock ledger (opening + receipts − issues ± adjustments = closing), each row linked to its source doc.
- **M8** Sales register and stock report, exportable to CSV/Excel.

### Should have
- **S1** Purchases and suppliers. **S2** Payments, outstanding and ageing. **S3** Cost per packet with overheads.
- **S4** GST summary (GSTR-1 / 3B shaped). **S5** Variance alerts beyond tolerance. **S6** Owner dashboard.

> S1 (purchase) and S3 (cost) are needed by benchmark steps 1, 7 and 8, so a minimal version is built **with** the must-haves.

> **Minimal offline order queue** (localStorage + `Idempotency-Key`) is built in P8 with the salesman UI, because
> §4.1 calls it "strongly preferred". Lot/expiry *fields* exist from day one (stretch only switches FEFO on).

### Stretch (only after the benchmark is green)
FEFO dispatch · production planning from pending orders · reorder alerts · Tally export ·
GPS visit log · e-Invoice/e-Way Bill mock · Tamil UI.

## 4. Benchmark: expected numbers (asserted in `tests/benchmark/`)

Master data and steps: see [PROBLEM.md §5](PROBLEM.md). Factory state = Tamil Nadu (code 33). GST 5%.

| # | Check | Expected | Derivation |
| --- | --- | --- | --- |
| B1 | Flour closing | **120 kg** | 100 + 60 − 40 |
| B2 | Oil closing | **19.5 L** | 30 − 10.5 |
| B3 | Spice mix closing | **3.8 kg** | 5 − 1.2 (not asked, asserted anyway) |
| B4 | Pouches closing | **306 pcs** | 500 − 188 used − 6 damaged |
| B5 | Cartons closing | **21 pcs** | 30 − 9 (not asked, asserted anyway) |
| B6 | FG after run | **238 pkts** | 50 + 188 |
| B7 | FG after Retailer A dispatch | **88 pkts** | 238 − 150 |
| B8 | Yield variance | **−6.00 %, flagged** | (188 − 200) / 200 |
| B9 | Oil variance | **+5.00 %, flagged** | (10.5 − 10) / 10 |
| B10 | Retailer A invoice | **₹7,500.00 + 187.50 CGST + 187.50 SGST = ₹7,875.00** | 150 × 50; 2.5% + 2.5% |
| B11 | Retailer A outstanding | **₹3,875.00** | 7,875 − 4,000 |
| B12 | Distributor B | **shortage 32 flagged**; if invoiced: IGST 5% | 120 − 88. 120 × 50 = 6,000 + 300 IGST = 6,300 |
| B13 | Cost per packet | **₹31.14** (proposed, see below) | weighted average + direct overheads per run |

Extra checks asserted alongside: B9b pouch −3.00% **not** flagged (A2 boundary) · B10b invoice no `FF/2026-27/0001` ·
B12b Distributor B tax preview INTER, IGST ₹300, total ₹6,300 · ledger reconciles · no orphan movements · salesman gets 403 on approve.

### B13: proposed cost per packet (weighted average cost, overheads charged to the run)
- Flour WAC at issue = (100×42 + 60×45) / 160 = 6,900 / 160 = **₹43.125/kg** → 40 kg = ₹1,725.00
- Oil 10.5 × 140 = ₹1,470.00 · Spice 1.2 × 200 = ₹240.00
- Pouches 194 × 2.50 = ₹485.00 (damaged pouches are a normal loss, charged to the run)
- Cartons 9 × 15 = ₹135.00
- **Materials ₹4,055.00** + labour ₹1,200 + gas/power ₹600 = **₹5,855.00**
- ÷ 188 good packets = **₹31.1436 → ₹31.14** · margin vs ₹50 = **₹18.86 (37.7%)**

## 5. Assumptions and ambiguities (to copy into the README)

| ID | Ambiguity | Assumption (proposed) |
| --- | --- | --- |
| A1 | Variance basis | Planned qty = BOM standard × batches run. Variance % = (actual − planned) / planned. |
| A2 | "Beyond 3%" | Flag when \|variance\| **> 3.00%** strictly. Tolerance is configurable per item. |
| A3 | Pouch variance | 194 used vs 200 standard = −3.00% → **not flagged** under A2. (Against good output, 194 vs 188 = +3.19%. We report the yield loss separately as B8.) |
| A4 | Cartons | 9 used vs 10 standard = −10% under-use, flagged. 188 pkts = 9 full cartons + 8 loose. Shown as info, not as a loss. |
| A5 | Opening FG cost | No history is given, so the 50 opening packets are valued at **standard material cost at opening rates**: (40×42 + 10×140 + 1.2×200 + 200×2.50 + 10×15) / 200 = **₹19.85/pkt**. Affects stock value and COGS only, not B13. |
| A6 | Valuation | Weighted average cost (moving, recomputed on each receipt). Simple, auditable, standard for fungible materials. |
| A7 | Overheads | Labour and gas/power are entered against a specific run and divided by **good** output. Monthly overheads (if any) are allocated by good packets produced. |
| A8 | Rounding | Tax computed per invoice line, rounded half-up to the paisa. No rupee round-off in the benchmark. |
| A9 | Insufficient stock | An order can't be approved beyond available FG. Admin chooses: approve partial (88), hold, or flag for production. |
| A10 | Wastage of oil/spice | Issued qty is treated as fully consumed (no return-to-store) unless a return movement is posted. |
| A11 | Units | Each item has one base unit (g, ml, pcs). kg/L/carton are conversions. Packets of FG are the FG base unit. |
| A12 | Invoice numbering | `FF/<FY>/<seq>` e.g. `FF/2026-27/0001`, gapless per FY. Cancelled numbers stay used (credit note issued). |
| A13 | Lots vs cost | Every movement carries a lot (batch no, expiry) for traceability. Lots are drawn FIFO by receipt; FEFO is a stretch toggle. **Cost is WAC per item, not per lot.** |
| A14 | Overheads timing | Benchmark step 8 adds overheads after dispatch, so they post as a value-only `COST_ADJUST` on the run's FG lot. COGS already booked for Retailer A is not restated. |
| A15 | Purchase GST | Purchase rates are taken as tax-exclusive. Input GST is recorded on the purchase but not used in costing. |
| A16 | Shelf life | Not given. Murukku is seeded with **90 days**, so a run's FG lot expires 90 days after the run date. Configurable per item. |
| A17 | Opening date | Opening stock is dated **31 Oct 2026**, the day before the benchmark month, so November reports show it as the opening balance. |
| A18 | Overhead date | Overheads entered after a run are dated on the **run date**, so the run's cost (and its FG lot's value) is complete as of the day it was made. |
| H1 | Time budget | About 2 days at about 6 focused h/day (the hours/day were not specified). The plan is sized for about 13 h and has explicit cut lines. |
