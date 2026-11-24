import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import PurchaseCard from "../components/PurchaseCard.jsx";
import { DISPLAY_UNIT, decMul, inr, localToday, toPaise } from "../format.js";
import { Banner, Button, Card, Field, input } from "../ui.jsx";

// A run is two API calls (docs/architecture.md section 5):
//   start    = POST /production-runs            issues the RAW materials actually taken from store
//   complete = POST /production-runs/{id}/complete  good output + PACKAGING actually used + damaged
// Every quantity is prefilled with the BOM plan but stays editable, because the variance is the
// difference between the plan and what the floor really used (benchmark: oil 10.5 l, pouches 194).

// BOM quantities arrive in base units (g, ml, pcs); show and send them in kg / l where that reads better.
function planLine(line, batches) {
  const [uom, factor] = DISPLAY_UNIT[line.uom] || [line.uom, "1"];
  return {
    item_id: line.item_id,
    code: line.item_code,
    uom,
    planned: decMul(decMul(line.qty, factor), batches),
  };
}

const validQty = (s) => /^\d+(\.\d+)?$/.test(String(s).trim());

export default function ProductionPage() {
  const { auth } = useAuth();
  const token = auth.token;
  const [boms, setBoms] = useState([]);
  const [kinds, setKinds] = useState({}); // item_id -> RAW | PACKAGING | FG
  const [bomId, setBomId] = useState("");
  const [batches, setBatches] = useState("1");
  const [issued, setIssued] = useState({}); // item_id -> qty typed at start (raw)
  const [output, setOutput] = useState("");
  const [used, setUsed] = useState({}); // item_id -> packaging used, including damaged
  const [damaged, setDamaged] = useState({}); // item_id -> damaged (info only)
  const [labour, setLabour] = useState("");
  const [power, setPower] = useState("");
  const [run, setRun] = useState(null);
  const [cost, setCost] = useState(null);
  const [variance, setVariance] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api("/boms", { token }), api("/items", { token })])
      .then(([b, items]) => {
        setBoms(b);
        setKinds(Object.fromEntries(items.map((i) => [i.id, i.kind])));
      })
      .catch((e) => setError(e.message));
  }, [token]);

  const bom = boms.find((b) => b.id === Number(bomId));
  const okBatches = validQty(batches) && Number(batches) > 0;
  const plan = bom && okBatches ? bom.lines.map((l) => planLine(l, batches)) : [];
  const raw = plan.filter((l) => kinds[l.item_id] === "RAW");
  const packaging = plan.filter((l) => kinds[l.item_id] === "PACKAGING");
  const qtyOf = (map, l) => (map[l.item_id] ?? l.planned).trim();

  const refresh = useCallback(
    async (runId) => {
      const [c, v] = await Promise.all([
        api(`/production-runs/${runId}/cost`, { token }),
        api(`/production-runs/${runId}/variance`, { token }),
      ]);
      setCost(c);
      setVariance(v);
    },
    [token],
  );

  async function guard(fn) {
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e.message);
    }
  }

  const start = () =>
    guard(async () => {
      const issues = raw.map((l) => ({ item_id: l.item_id, qty: qtyOf(issued, l), uom: l.uom }));
      if (issues.some((i) => !validQty(i.qty)))
        throw new Error("Enter every issued quantity as a number.");
      const created = await api("/production-runs", {
        method: "POST",
        token,
        body: { bom_id: bom.id, batches: String(batches).trim(), run_date: localToday(), issues },
      });
      setRun(created);
      setIssued({});
      setCost(null);
      setVariance(null);
    });

  const complete = () =>
    guard(async () => {
      const issues = packaging.map((l) => ({
        item_id: l.item_id,
        qty: qtyOf(used, l),
        uom: l.uom,
      }));
      const bad = packaging.map((l) => (damaged[l.item_id] || "").trim()).filter(Boolean);
      if (
        !validQty(output) ||
        issues.some((i) => !validQty(i.qty)) ||
        bad.some((d) => !validQty(d))
      ) {
        throw new Error("Enter output, packaging used and damaged as numbers.");
      }
      const done = await api(`/production-runs/${run.id}/complete`, {
        method: "POST",
        token,
        body: {
          output_qty: String(output).trim(),
          issues,
          damaged: packaging
            .filter((l) => Number(damaged[l.item_id] || 0) > 0)
            .map((l) => ({ item_id: l.item_id, qty: damaged[l.item_id].trim(), uom: l.uom })),
        },
      });
      setRun(done);
      setOutput("");
      setUsed({});
      setDamaged({});
      await refresh(done.id);
    });

  const addOverheads = () =>
    guard(async () => {
      const lines = [];
      for (const [kind, text] of [
        ["LABOUR", labour],
        ["GAS_POWER", power],
      ]) {
        if (!text.trim()) continue;
        const paise = toPaise(text);
        if (!paise) throw new Error("Overheads are rupee amounts, e.g. 1200 or 600.50.");
        lines.push({ kind, amount_paise: paise });
      }
      if (lines.length === 0) return;
      await api(`/production-runs/${run.id}/overheads`, { method: "POST", token, body: { lines } });
      setLabour("");
      setPower("");
      await refresh(run.id);
    });

  return (
    <>
      <h1 className="text-xl font-semibold">Production</h1>
      <Banner>{error}</Banner>
      <PurchaseCard token={token} />

      {!run || run.status === "COMPLETED" ? (
        <Card title="Start a run">
          <div className="space-y-3">
            <Field label="Recipe (BOM)">
              <select className={input} value={bomId} onChange={(e) => setBomId(e.target.value)}>
                <option value="">Select a BOM…</option>
                {boms.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.code} → {b.item_code}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Batches">
              <input
                className={input}
                value={batches}
                onChange={(e) => setBatches(e.target.value)}
              />
            </Field>
            {raw.length > 0 && (
              <QtyTable
                caption="Raw materials issued now (planned is BOM × batches)"
                lines={raw}
                cols={[["Issued", issued, setIssued]]}
              />
            )}
            {packaging.length > 0 && (
              <p className="text-sm text-slate-500">
                Packaging ({packaging.map((l) => l.code).join(", ")}) is counted when you complete
                the run.
              </p>
            )}
            <Button disabled={!bom || !okBatches} onClick={start}>
              Start run (issue raw materials)
            </Button>
          </div>
        </Card>
      ) : null}

      {run && run.status === "DRAFT" && (
        <Card title={`${run.run_no}: record output`}>
          <div className="space-y-3">
            <Field label={`Good output (pkt) — expected ${Number(run.planned_qty)}`}>
              <input className={input} value={output} onChange={(e) => setOutput(e.target.value)} />
            </Field>
            {packaging.length > 0 && (
              <QtyTable
                caption="Packaging used (including damaged)"
                lines={packaging}
                cols={[
                  ["Used", used, setUsed],
                  ["Damaged", damaged, setDamaged, "0"],
                ]}
              />
            )}
            <Button disabled={!output} onClick={complete}>
              Complete run
            </Button>
          </div>
        </Card>
      )}

      {run && run.status === "COMPLETED" && (
        <Card title={`${run.run_no}: variance, overheads & cost`}>
          {variance && <VarianceTable variance={variance} />}
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Field label="Labour (₹)">
              <input className={input} value={labour} onChange={(e) => setLabour(e.target.value)} />
            </Field>
            <Field label="Gas / power (₹)">
              <input className={input} value={power} onChange={(e) => setPower(e.target.value)} />
            </Field>
          </div>
          <Button className="mt-3" variant="ghost" onClick={addOverheads}>
            Add overheads
          </Button>
          {cost && (
            <dl className="mt-4 grid grid-cols-2 gap-1 text-sm">
              <dt className="text-slate-500">Material</dt>
              <dd className="text-right">{inr(cost.material_paise)}</dd>
              <dt className="text-slate-500">Overhead</dt>
              <dd className="text-right">{inr(cost.overhead_paise)}</dd>
              <dt className="font-medium">Cost / packet</dt>
              <dd className="text-right font-medium">{inr(cost.cost_per_unit_paise)}</dd>
            </dl>
          )}
        </Card>
      )}
    </>
  );
}

// Planned column + one editable column per entry in `cols` ([label, values, setValues, default]).
function QtyTable({ caption, lines, cols }) {
  return (
    <table className="w-full text-sm">
      <caption className="mb-1 text-left text-slate-500">{caption}</caption>
      <thead>
        <tr className="text-left text-slate-500">
          <th className="py-1 font-medium">Item</th>
          <th className="py-1 font-medium">Planned</th>
          {cols.map(([label]) => (
            <th key={label} className="py-1 font-medium">
              {label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {lines.map((l) => (
          <tr key={l.item_id} className="border-t border-slate-100">
            <td className="py-1 pr-2">{l.code}</td>
            <td className="py-1 pr-2">
              {l.planned} {l.uom}
            </td>
            {cols.map(([label, values, setValues, dflt]) => (
              <td key={label} className="py-1 pr-2">
                <input
                  aria-label={`${label} ${l.code} (${l.uom})`}
                  className={`${input} w-24`}
                  inputMode="decimal"
                  value={values[l.item_id] ?? dflt ?? l.planned}
                  onChange={(e) => setValues((v) => ({ ...v, [l.item_id]: e.target.value }))}
                />
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// "10500.000" ml -> "10.5 l"; exact (string maths), display only.
function show(qty, uom) {
  const [unit, factor] = DISPLAY_UNIT[uom] || [uom, "1"];
  return `${decMul(qty, factor)} ${unit}`; // decMul drops trailing zeros: "194.000" -> "194"
}

const pct = (bp) => `${bp > 0 ? "+" : ""}${(bp / 100).toFixed(2)}%`;

function VarianceTable({ variance }) {
  const rows = [
    { code: "Yield (good output)", uom: "pkt", ...variance.yield, damaged_qty: null },
    ...variance.lines,
  ];
  return (
    <table className="w-full text-sm">
      <caption className="mb-1 text-left text-slate-500">
        Planned vs actual (flag beyond tolerance)
      </caption>
      <thead>
        <tr className="text-left text-slate-500">
          <th className="py-1 font-medium">Item</th>
          <th className="py-1 font-medium">Planned</th>
          <th className="py-1 font-medium">Actual</th>
          <th className="py-1 font-medium">Variance</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.item_code || r.code} className="border-t border-slate-100">
            <td className="py-1 pr-2">{r.item_code || r.code}</td>
            <td className="py-1 pr-2">{show(r.planned_qty, r.uom)}</td>
            <td className="py-1 pr-2">
              {show(r.actual_qty, r.uom)}
              {Number(r.damaged_qty) > 0 && ` (${show(r.damaged_qty, r.uom)} damaged)`}
            </td>
            <td className={`py-1 ${r.flagged ? "font-medium text-rose-600" : "text-emerald-700"}`}>
              {pct(r.variance_bp)}
              {r.flagged ? " · flagged" : ""}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
