import { useCallback, useEffect, useState } from "react";

import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { inr } from "../format.js";
import { Banner, Button, Card, Field, input } from "../ui.jsx";

const today = () => new Date().toISOString().slice(0, 10);

export default function ProductionPage() {
  const { auth } = useAuth();
  const token = auth.token;
  const [boms, setBoms] = useState([]);
  const [bomId, setBomId] = useState("");
  const [batches, setBatches] = useState("1");
  const [output, setOutput] = useState("");
  const [labour, setLabour] = useState("");
  const [power, setPower] = useState("");
  const [run, setRun] = useState(null);
  const [cost, setCost] = useState(null);
  const [variance, setVariance] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/boms", { token })
      .then(setBoms)
      .catch((e) => setError(e.message));
  }, [token]);

  const bom = boms.find((b) => b.id === Number(bomId));

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
      const issues = bom.lines.map((l) => ({
        item_id: l.item_id,
        qty: String(Number(l.qty) * Number(batches)),
        uom: l.uom,
      }));
      const created = await api("/production-runs", {
        method: "POST",
        token,
        body: { bom_id: bom.id, batches: String(batches), run_date: today(), issues },
      });
      setRun(created);
      setCost(null);
      setVariance(null);
    });

  const complete = () =>
    guard(async () => {
      const done = await api(`/production-runs/${run.id}/complete`, {
        method: "POST",
        token,
        body: { output_qty: String(output) },
      });
      setRun(done);
      await refresh(done.id);
    });

  const addOverheads = () =>
    guard(async () => {
      const lines = [];
      if (labour) lines.push({ kind: "LABOUR", amount_paise: Math.round(Number(labour) * 100) });
      if (power) lines.push({ kind: "GAS_POWER", amount_paise: Math.round(Number(power) * 100) });
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
            {bom && (
              <p className="text-sm text-slate-500">
                Per batch: {bom.lines.map((l) => `${l.qty} ${l.uom} ${l.item_code}`).join(", ")} →{" "}
                {bom.output_qty} {bom.output_uom}
              </p>
            )}
            <Field label="Batches">
              <input
                className={input}
                value={batches}
                onChange={(e) => setBatches(e.target.value)}
              />
            </Field>
            <Button disabled={!bom} onClick={start}>
              Start run (issue materials)
            </Button>
          </div>
        </Card>
      ) : null}

      {run && run.status === "DRAFT" && (
        <Card title={`${run.run_no}: record output`}>
          <div className="space-y-3">
            <Field label="Good output (pkt)">
              <input className={input} value={output} onChange={(e) => setOutput(e.target.value)} />
            </Field>
            <Button disabled={!output} onClick={complete}>
              Complete run
            </Button>
          </div>
        </Card>
      )}

      {run && run.status === "COMPLETED" && (
        <Card title={`${run.run_no}: overheads & cost`}>
          <div className="grid grid-cols-2 gap-3">
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
          {variance && (
            <p className="mt-3 text-sm">
              Yield: {variance.yield.actual_qty} / {variance.yield.planned_qty} ·{" "}
              <span className={variance.yield.flagged ? "text-rose-600" : "text-emerald-600"}>
                {(variance.yield.variance_bp / 100).toFixed(2)}%
                {variance.yield.flagged ? " (flagged)" : ""}
              </span>
            </p>
          )}
        </Card>
      )}
    </>
  );
}
