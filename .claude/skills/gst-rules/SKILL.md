---
name: gst-rules
description: Indian GST rules as implemented in FactoryFlow. Covers CGST/SGST vs IGST by place of supply, per-line rounding in paise, invoice numbering by financial year, credit notes, and GSTR-1/GSTR-3B report shapes. Use when touching billing, invoices, credit notes, tax previews, the invoice PDF, or GST reports.
---

# GST rules (prototype scope)

Expected benchmark numbers: docs/project_spec.md (B10, B12, B12b). Mechanism: docs/architecture.md section 5.

## Determining tax type
- Company state code comes from company settings (Tamil Nadu = `33`). It is **not hard-coded**.
- **Place of supply = the customer's state** (B2B goods delivered to the buyer).
- `supply_type = INTRA` if POS == company state, else `INTER`.
- INTRA → CGST + SGST, each at **half** the rate. INTER → IGST at the full rate. Never both.
- GSTIN, if present, must be 15 characters, and its first 2 digits should equal the customer's state code. Warn on mismatch; don't block.

## Arithmetic (all in `core.gst`, pure, unit-tested)
- Rates are basis points: 5% = `500`.
- Per line: `taxable = qty × rate_paise`. This is exact, because qty is a whole number of packets. A fractional total is an error.
- INTRA: `cgst = sgst = half_up(taxable × (bp / 2) / 10000)`. INTER: `igst = half_up(taxable × bp / 10000)`.
- Invoice totals = sums of the line amounts. **Never recompute tax on the total.**
- No rupee round-off line in the prototype (A8). If one is added later, it's a separate `round_off_paise` field.
- Required test cases: B10 (750000 → 18750 + 18750), an odd-paise taxable where each half rounds separately, INTER, 0%, and 12%.

## Invoice numbering
- FY runs 1 April to 31 March: `fy = "2026-27"` for any date from 2026-04-01 to 2027-03-31.
- `invoice_no = f"FF/{fy}/{seq:04d}"`. `seq` comes from `invoice_sequence` locked `FOR UPDATE` inside the same transaction, so it is gapless.
- The invoice date is IST (`Asia/Kolkata`), not UTC.

## Lifecycle
- Statuses: `POSTED → CANCELLED` only. A posted invoice is **never edited or deleted**.
- Cancel = create a `credit_note` (its own FY series `FF/CN/{fy}/{seq}`) + post REVERSAL stock movements if dispatched + audit row.

## Reports
- **GSTR-1:** B2B table (GSTIN, invoice no/date, POS, taxable, rate, IGST/CGST/SGST), HSN summary (HSN, UQC, qty, taxable, tax), credit-note table.
- **GSTR-3B 3.1(a):** total taxable outward supplies and IGST/CGST/SGST, net of credit notes, for the period.
- All report figures come from `invoice_line` / `credit_note_line`, never from the PDF.
