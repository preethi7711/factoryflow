import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import PurchaseCard from "../components/PurchaseCard.jsx";
import { CostBreakdown, ProcessLine, VarianceBars } from "../components/RunVisuals.jsx";
import ItemArt from "../components/SnackArt.jsx";
import { DISPLAY_UNIT, decMul, localToday, toPaise } from "../format.js";
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
  const [itemsById, setItemsById] = useState({}); // item_id -> item (kind, name, sale price)
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
        setItemsById(Object.fromEntries(items.map((i) => [i.id, i])));
      })
      .catch((e) => setError(e.message));
  }, [token]);

  const bom = boms.find((b) => b.id === Number(bomId));
  const okBatches = validQty(batches) && Number(batches) > 0;
  const plan = bom && okBatches ? bom.lines.map((l) => planLine(l, batches)) : [];
  const kindOf = (id) => itemsById[id]?.kind;
  const raw = plan.filter((l) => kindOf(l.item_id) === "RAW");
  const packaging = plan.filter((l) => kindOf(l.item_id) === "PACKAGING");
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
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-3xl font-extrabold">Production floor</h1>
        {run && (
          <p className="text-sm text-choc-500">
            {run.run_no} · {run.item_code} · {Number(run.batches)} batch
            {Number(run.batches) === 1 ? "" : "es"}
          </p>
        )}
      </div>
      <ProcessLine run={run} />
      <Banner>{error}</Banner>

      {run && run.status === "DRAFT" && (
        <Card title={`${run.run_no}: record output`}>
          <div className="space-y-3">
            <Field label={`Good packets (expected ${Number(run.planned_qty)})`}>
              <input
                className={input}
                inputMode="numeric"
                value={output}
                onChange={(e) => setOutput(e.target.value)}
              />
            </Field>
            {packaging.length > 0 && (
              <QtyTable
                caption="Packaging used (damaged ones included)"
                lines={packaging}
                itemsById={itemsById}
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
        <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
          {variance && (
            <Card title={`${run.run_no}: planned vs actual`}>
              <VarianceBars
                variance={variance}
                names={Object.fromEntries(Object.values(itemsById).map((i) => [i.id, i.name]))}
              />
              <p className="mt-3 text-xs text-choc-500">
                Pale bar = recipe plan, solid bar = what the floor used (read from the stock
                ledger). Red means the difference is beyond the item&apos;s tolerance.
              </p>
            </Card>
          )}
          {
            <Card title="Overheads and cost">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Labour (₹)">
                  <input
                    className={input}
                    inputMode="decimal"
                    value={labour}
                    onChange={(e) => setLabour(e.target.value)}
                  />
                </Field>
                <Field label="Gas / power (₹)">
                  <input
                    className={input}
                    inputMode="decimal"
                    value={power}
                    onChange={(e) => setPower(e.target.value)}
                  />
                </Field>
              </div>
              <Button className="mt-3" variant="ghost" onClick={addOverheads}>
                Add overheads
              </Button>
              {cost && (
                <div className="mt-4">
                  <CostBreakdown
                    cost={cost}
                    salePricePaise={itemsById[run.item_id]?.sale_price_paise ?? null}
                  />
                </div>
              )}
            </Card>
          }
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {!run || run.status === "COMPLETED" ? (
          <Card title={run ? "Start the next run" : "Start a run"}>
            <div className="space-y-3">
              <div className="grid grid-cols-[1fr_7rem] gap-3">
                <Field label="Recipe (BOM)">
                  <select
                    className={input}
                    value={bomId}
                    onChange={(e) => setBomId(e.target.value)}
                  >
                    <option value="">Select a recipe…</option>
                    {boms.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.item_code} ({b.code})
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Batches">
                  <input
                    className={input}
                    inputMode="decimal"
                    value={batches}
                    onChange={(e) => setBatches(e.target.value)}
                  />
                </Field>
              </div>
              {bom && (
                <p className="text-sm text-choc-500">
                  One batch should give {Number(bom.output_qty)} {bom.output_uom}.
                </p>
              )}
              {raw.length > 0 && (
                <QtyTable
                  caption="Raw materials to issue now (planned = recipe × batches)"
                  lines={raw}
                  itemsById={itemsById}
                  cols={[["Issued", issued, setIssued]]}
                />
              )}
              {packaging.length > 0 && (
                <p className="text-sm text-choc-500">
                  Packaging ({packaging.map((l) => itemsById[l.item_id]?.name || l.code).join(", ")}
                  ) is counted when you complete the run.
                </p>
              )}
              <Button disabled={!bom || !okBatches} onClick={start}>
                Start run and issue raw materials
              </Button>
            </div>
          </Card>
        ) : null}

        {(!run || run.status === "COMPLETED") && <PurchaseCard token={token} />}
      </div>
    </>
  );
}

// Planned column + one editable column per entry in `cols` ([label, values, setValues, default]).
function QtyTable({ caption, lines, cols, itemsById }) {
  return (
    <table className="w-full text-sm">
      <caption className="mb-1 text-left text-choc-500">{caption}</caption>
      <thead>
        <tr className="text-left text-choc-500">
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
          <tr key={l.item_id} className="border-t border-line">
            <td className="py-1 pr-2">
              <span className="flex items-center gap-2">
                <ItemArt code={l.code} className="h-8 w-8 shrink-0" />
                {itemsById[l.item_id]?.name || l.code}
              </span>
            </td>
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
