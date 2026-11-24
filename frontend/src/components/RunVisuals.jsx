// Production visuals. Every shape here is drawn from API data (the run, /variance, /cost); nothing is
// simulated. Bar lengths use Number() only to size pixels; the figures printed beside them are the exact
// strings and paise from the server.

import { inr, showQty as show } from "../format.js";
import ItemArt from "./SnackArt.jsx";

const pct = (bp) => `${bp > 0 ? "+" : ""}${(bp / 100).toFixed(2)}%`;

// Store -> Kadai -> Packing -> Finished goods. Which stations are lit depends only on run.status:
// no run: nothing lit; DRAFT: raw materials have left the store and the batch is in the kadai;
// COMPLETED: packaging issued and the good packets are in their finished-goods lot.
export function ProcessLine({ run }) {
  const status = run?.status;
  const done = {
    store: Boolean(run),
    kadai: status === "COMPLETED",
    packing: status === "COMPLETED",
    fg: status === "COMPLETED",
  };
  const stations = [
    ["store", "Store", "FLOUR", run ? "Raw materials issued" : "Waiting"],
    ["kadai", "Kadai", "OIL", status === "DRAFT" ? "Frying now" : done.kadai ? "Fried" : "Idle"],
    ["packing", "Packing", "POUCH", done.packing ? "Packed" : "Idle"],
    [
      "fg",
      "Finished goods",
      "MURUKKU",
      done.fg ? `${Number(run.good_qty)} pkt in lot ${run.output_lot_no}` : "Idle",
    ],
  ];
  return (
    <div className="rounded-2xl border border-line bg-cream p-4" aria-label="Run progress">
      <ol className="grid grid-cols-4 gap-2">
        {stations.map(([key, name, art, note], i) => {
          const lit = done[key] || (key === "kadai" && status === "DRAFT");
          const active = key === "kadai" && status === "DRAFT";
          return (
            <li key={key} className="relative flex flex-col items-center text-center">
              {i > 0 && <Pipe flowing={active} lit={lit} />}
              <span
                className={`relative z-[1] flex h-14 w-14 items-center justify-center rounded-full border-2 ${
                  lit ? "border-turmeric-700 bg-paper" : "border-line bg-paper opacity-50 grayscale"
                }`}
              >
                <ItemArt code={art} className="h-9 w-9" />
              </span>
              <span className="mt-1 text-sm font-semibold">{name}</span>
              <span
                className={`text-xs ${active ? "font-semibold text-turmeric-700" : "text-choc-500"}`}
              >
                {note}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// The connector before a station; dashes run only while the batch is actually in progress.
function Pipe({ flowing, lit }) {
  return (
    <svg className="absolute right-1/2 top-7 h-1 w-full -translate-y-1/2" aria-hidden="true">
      <line
        x1="0"
        y1="2"
        x2="100%"
        y2="2"
        stroke={lit ? "#9A6608" : "#EADFCB"}
        strokeWidth="4"
        strokeDasharray={flowing ? "8 4" : undefined}
        className={flowing ? "animate-flow" : undefined}
      />
    </svg>
  );
}

// One row per material plus yield: a pale bar for the plan, a solid one for what really happened.
export function VarianceBars({ variance, names = {} }) {
  const rows = [
    {
      key: "yield",
      label: "Good output (yield)",
      code: "MURUKKU",
      uom: "pkt",
      ...variance.yield,
    },
    ...variance.lines.map((l) => ({
      key: l.item_id,
      label: names[l.item_id] || l.item_code,
      code: l.item_code,
      ...l,
    })),
  ];
  return (
    <ul className="space-y-3">
      {rows.map((r) => {
        const planned = Number(r.planned_qty);
        const actual = Number(r.actual_qty);
        const max = Math.max(planned, actual) || 1;
        return (
          <li key={r.key} className="grid grid-cols-[2.5rem_1fr_auto] items-center gap-3">
            <ItemArt code={r.code} className="h-10 w-10" />
            <div className="min-w-0">
              <p className="flex justify-between gap-2 text-sm">
                <span className="truncate font-semibold">{r.label}</span>
                <span className="num text-choc-500">
                  {show(r.actual_qty, r.uom)} of {show(r.planned_qty, r.uom)}
                  {Number(r.damaged_qty) > 0 && `, ${show(r.damaged_qty, r.uom)} damaged`}
                </span>
              </p>
              <div className="mt-1 space-y-0.5" aria-hidden="true">
                <div
                  className="h-1.5 rounded-full bg-choc-100"
                  style={{ width: `${(planned / max) * 100}%` }}
                />
                <div
                  className={`h-2.5 rounded-full transition-[width] duration-500 ${r.flagged ? "bg-chilli-500" : "bg-leaf-500"}`}
                  style={{ width: `${(actual / max) * 100}%` }}
                />
              </div>
            </div>
            <span
              className={`num w-24 text-right text-sm font-semibold ${r.flagged ? "text-chilli-700" : "text-leaf-700"}`}
            >
              {pct(r.variance_bp)}
              <span className="block text-[11px] font-medium">
                {r.flagged ? "Flagged" : "Within tolerance"}
              </span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

// Materials + overheads = run cost; ÷ good packets = cost per packet; against the selling price = margin.
// All money is integer paise from GET /cost; the margin is one integer subtraction.
export function CostBreakdown({ cost, salePricePaise }) {
  const total = cost.total_paise || 1;
  const margin = salePricePaise != null ? salePricePaise - cost.cost_per_unit_paise : null;
  return (
    <div className="space-y-3">
      <div className="flex h-4 overflow-hidden rounded-full bg-line" aria-hidden="true">
        <div className="bg-choc-700" style={{ width: `${(cost.material_paise / total) * 100}%` }} />
        <div
          className="bg-turmeric-500"
          style={{ width: `${(cost.overhead_paise / total) * 100}%` }}
        />
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <dt className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-choc-700" /> Materials (weighted average)
        </dt>
        <dd className="num text-right">{inr(cost.material_paise)}</dd>
        <dt className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-turmeric-500" /> Labour, gas and power
        </dt>
        <dd className="num text-right">{inr(cost.overhead_paise)}</dd>
        <dt className="font-semibold">Run cost ÷ {Number(cost.good_qty)} good packets</dt>
        <dd className="num text-right font-semibold">{inr(cost.total_paise)}</dd>
      </dl>
      <div className="flex flex-wrap items-end justify-between gap-3 rounded-xl bg-choc-900 px-4 py-3 text-cream">
        <div>
          <p className="text-xs text-choc-100">Cost per packet</p>
          <p className="num font-display text-3xl font-extrabold">
            {inr(cost.cost_per_unit_paise)}
          </p>
        </div>
        {margin != null && (
          <div className="text-right">
            <p className="text-xs text-choc-100">Margin at {inr(salePricePaise)}</p>
            <p
              className={`num font-display text-xl font-extrabold ${margin >= 0 ? "text-turmeric-300" : "text-chilli-100"}`}
            >
              {inr(margin)}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
