import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import ItemArt from "../components/SnackArt.jsx";
import { inr, localToday, showQty } from "../format.js";
import { Banner, Button, Card, Field, input, Pill } from "../ui.jsx";

// Owner dashboard (S6). Four headline numbers for the month, plus FG stock on hand and a short
// ageing summary pulled from the same reports the detailed pages show, so nothing can disagree.

function monthDefaults() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  return [localToday(first), localToday(last)];
}

export default function DashboardPage() {
  const { auth } = useAuth();
  const token = auth.token;
  const [[from, to], setRange] = useState(monthDefaults);
  const [dash, setDash] = useState(null);
  const [ageing, setAgeing] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [d, a] = await Promise.all([
        api(`/reports/dashboard?from=${from}&to=${to}`, { token }),
        api(`/reports/ageing?from=${from}&to=${to}`, { token }),
      ]);
      setDash(d);
      setAgeing(a);
    } catch (e) {
      setError(e.message);
    }
  }, [token, from, to]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <>
      <div>
        <h1 className="text-3xl font-extrabold">Factory at a glance</h1>
        <p className="text-sm text-choc-500">
          All figures are read from the ledger, the invoices and the payments for the period you
          pick.
        </p>
      </div>

      <Card title="Period">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="From">
            <input
              className={input}
              type="date"
              value={from}
              onChange={(e) => setRange([e.target.value, to])}
            />
          </Field>
          <Field label="To">
            <input
              className={input}
              type="date"
              value={to}
              onChange={(e) => setRange([from, e.target.value])}
            />
          </Field>
          <Button onClick={load}>Refresh</Button>
        </div>
      </Card>

      <Banner>{error}</Banner>

      {dash && dash.flagged_variances > 0 && (
        <Banner kind="info">
          {dash.flagged_variances} variance{dash.flagged_variances === 1 ? " is" : "s are"}{" "}
          beyond tolerance this period. See <strong>Stock &amp; reports → Variance alerts</strong>.
        </Banner>
      )}

      {dash && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              tone="turmeric"
              label="Sales (period)"
              value={inr(dash.sales_paise)}
              footer={`${dash.invoices_count} invoice${dash.invoices_count === 1 ? "" : "s"}`}
            />
            <Metric
              tone="leaf"
              label="Collections"
              value={inr(dash.collections_paise)}
              footer="Received in period"
            />
            <Metric
              tone="chilli"
              label="Outstanding"
              value={inr(dash.outstanding_paise)}
              footer={
                dash.outstanding_paise > 0 ? "Across live invoices" : "Nothing owed"
              }
            />
            <Metric
              tone="choc"
              label="FG value"
              value={inr(dash.fg_value_paise)}
              footer={`${dash.pending_orders} pending order${
                dash.pending_orders === 1 ? "" : "s"
              } · ${dash.completed_runs} run${dash.completed_runs === 1 ? "" : "s"}`}
            />
          </div>

          <Card title="Finished goods on hand">
            {dash.fg_lines.length === 0 ? (
              <p className="text-sm text-choc-500">No finished-goods items configured.</p>
            ) : (
              <ul className="space-y-2">
                {dash.fg_lines.map((line) => (
                  <li
                    key={line.item_code}
                    className="flex items-center justify-between gap-3 rounded-xl bg-cream px-3 py-2"
                  >
                    <span className="flex items-center gap-3">
                      <ItemArt code={line.item_code} name={line.name} className="h-10 w-10" />
                      <span>
                        <span className="block font-semibold">{line.name}</span>
                        <span className="text-xs text-choc-500">{line.item_code}</span>
                      </span>
                    </span>
                    <span className="text-right">
                      <span className="num block font-semibold">
                        {showQty(line.qty, line.uom)}
                      </span>
                      <span className="num text-xs text-choc-500">
                        {inr(line.value_paise)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </>
      )}

      {ageing && <AgeingSummary ageing={ageing} />}
    </>
  );
}

const TONE = {
  turmeric: "bg-turmeric-50 border-turmeric-100",
  leaf: "bg-leaf-50 border-leaf-100",
  chilli: "bg-chilli-50 border-chilli-100",
  choc: "bg-choc-100 border-line",
};

function Metric({ tone = "turmeric", label, value, footer }) {
  return (
    <section className={`rounded-2xl border p-4 ${TONE[tone]}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-choc-500">{label}</p>
      <p className="num mt-1 font-display text-3xl font-extrabold">{value}</p>
      {footer && <p className="mt-1 text-xs text-choc-500">{footer}</p>}
    </section>
  );
}

// A compact ageing panel: totals per bucket + the two or three oldest invoices, so the owner sees
// what's overdue without opening the full ageing report.
function AgeingSummary({ ageing }) {
  const buckets = [
    ["b0_30_paise", "0-30 days", "ok"],
    ["b31_60_paise", "31-60 days", "wait"],
    ["b61_90_paise", "61-90 days", "wait"],
    ["b91plus_paise", "91+ days", "bad"],
  ];
  const totals = ageing.totals || {};
  const total = totals.outstanding_paise || 0;
  const oldest = [...ageing.rows].sort((a, b) => b.age_days - a.age_days).slice(0, 3);
  return (
    <Card title="Receivables ageing">
      <div className="grid gap-2 sm:grid-cols-4">
        {buckets.map(([key, label, tone]) => (
          <div key={key} className="rounded-xl border border-line bg-cream p-3">
            <Pill tone={tone}>{label}</Pill>
            <p className="num mt-2 font-display text-xl font-extrabold">
              {inr(Number(totals[key] || 0))}
            </p>
          </div>
        ))}
      </div>
      <p className="mt-3 text-xs text-choc-500">
        Total outstanding: <span className="num font-semibold">{inr(total)}</span>
      </p>
      {oldest.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {oldest.map((row) => (
            <li
              key={row.invoice_no}
              className="flex items-center justify-between gap-2 rounded-xl bg-paper px-3 py-2"
            >
              <span>
                <span className="font-semibold">{row.invoice_no}</span>{" "}
                <span className="text-choc-500">{row.customer_code}</span>
              </span>
              <span className="flex items-center gap-2">
                <span className="num font-semibold">{inr(row.outstanding_paise)}</span>
                <Pill tone={row.age_days > 60 ? "bad" : row.age_days > 30 ? "wait" : "ok"}>
                  {row.age_days}d
                </Pill>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
