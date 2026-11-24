# Demo video script (target 6–7 min, limit 8)

Record on a **freshly seeded** database, either the live site right after seeding or locally after
`python -m app.seed`. Keep two browser windows: a phone-sized one (DevTools device mode, ~390 px) for
the salesman, and a desktop one for everyone else. Each step below is one benchmark step from
[PROBLEM.md §5](PROBLEM.md), in order.

## 0. Intro (0:00–0:30)
Show the login page. Say: "One system from salesman order to auditor report. Stock is an append-only
ledger, money is integer paise, and the whole scenario you're about to see is also an automated test."

## 1. Purchase (0:30–1:00), login `production`
Record a purchase: Flour Supplier, Flour, **60 kg at ₹45/kg**. Point at "≈ ₹2,700.00 before tax" and
the confirmation "Purchase #1 posted".

## 2–3. Production run (1:00–2:30), still `production`
1. Start a run: recipe Murukku 200 g, batches 1. The planned column shows the BOM (40 kg, 10 l, 1.2 kg).
2. Change **oil issued to 10.5**, then Start run.
3. Record output: good output **188**, pouches used **194**, damaged **6**, cartons used **9**, then Complete run.
4. Read the variance table aloud:
   - yield **−6.00% flagged**
   - oil **+5.00% flagged**
   - pouches −3.00% not flagged ("the brief says flag *beyond* 3%")
   - cartons −10% flagged (9 full cartons + 8 loose packets)

## 4. Salesman A order (2:30–3:15), phone window, `salesman_a`
Pick Retailer A, Murukku 200 g, **150**, then Place order. Show the queued → synced status.
Optional: toggle DevTools "Offline", place a second order, go back online, and show it sync **once**
(the idempotency key prevents a duplicate). If you do this, the order list also shows the extra order.

## 5. Approve, invoice, dispatch (3:15–4:30), desktop, `admin`
1. Approve the Retailer A order, then Raise invoice: **₹7,500 + ₹187.50 CGST + ₹187.50 SGST = ₹7,875**, number **FF/2026-27/0001**.
2. Open the invoice PDF and show the GSTIN, HSN and place of supply.
3. Dispatch. Say: "finished goods go from 238 to 88."

## 6. Distributor B shortage (4:30–5:00)
1. Log in as `salesman_b` (phone window) and order Distributor B **120**.
2. As `admin`, Approve. The screen shows **short by 32 (want 120, have 88)** and, from the tax preview, **₹6,000 + ₹300 IGST = ₹6,300** if it were invoiced.
3. Say: "Karnataka is another state, so it's IGST instead of CGST + SGST."

## 7. Payment (5:00–5:20), `admin`
Type **4000** in the amount box on the Retailer A order and click Record payment. The screen confirms: outstanding **₹3,875.00**.

## 8. Overheads and cost (5:20–6:00), `production`
Add labour **1200** and gas/power **600**. Show material ₹4,055, overhead ₹1,800, **cost per packet
₹31.14**. Explain: "weighted average flour cost ₹43.125/kg, damaged pouches charged to the run,
overheads divided by good output."

## 9. Month reports (6:00–7:00), `accountant`
1. Set the period to this month.
2. Show the stock summary: flour 120000 g (= 120 kg), oil 19500 ml (= 19.5 l), pouches 306, finished goods 88. Quantities are in base units and values in paise, straight from the ledger.
3. Download the sales register, stock ledger and production report as CSV/XLSX, and open one.
4. Close: "Every row in the stock ledger links to the purchase, run, dispatch or opening entry that caused it."

## Before recording
- [ ] Fresh seed (or a new DB). The steps above assume no earlier orders or runs.
- [ ] Put the salesman in a **separate browser or an incognito window**: logins in one browser
      profile share storage, so logging in as `salesman_b` there would sign the admin tab out.
- [ ] **Don't reload the admin tab between steps 5 and 7.** The raised invoice is held in that page
      (known gap), and the payment box needs it.
- [ ] Live site: open it a minute early so the cold start doesn't appear in the video.
- [ ] Browser zoom at 110–125% so the numbers are readable.
