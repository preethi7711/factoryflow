import { useEffect, useState } from "react";

import { api } from "../api/client.js";
import { DISPLAY_UNIT, inr, localToday, toPaise } from "../format.js";
import { Banner, Button, Card, Field, input } from "../ui.jsx";

// Benchmark step 1: "Record a purchase of 60 kg flour at ₹45/kg" (POST /purchases, production role).
// The rate is per the unit shown (₹/kg, ₹/l, ₹/pcs); the server converts to base units and values
// the receipt exactly (docs/architecture.md section 5, Purchase).
export default function PurchaseCard({ token, onPosted }) {
  const [suppliers, setSuppliers] = useState([]);
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({
    supplier_id: "",
    item_id: "",
    qty: "",
    rate: "",
    bill_no: "",
  });
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    Promise.all([api("/suppliers", { token }), api("/items", { token })])
      .then(([s, i]) => {
        setSuppliers(s);
        setItems(i.filter((x) => x.kind !== "FG"));
      })
      .catch((e) => setMsg({ kind: "error", text: e.message }));
  }, [token]);

  const item = items.find((i) => i.id === Number(form.item_id));
  const uom = item ? (DISPLAY_UNIT[item.base_uom] || [item.base_uom])[0] : "";
  const set = (patch) => setForm((f) => ({ ...f, ...patch }));

  async function save(e) {
    e.preventDefault();
    setMsg(null);
    const rate = toPaise(form.rate);
    if (!form.supplier_id || !item || !/^\d+(\.\d+)?$/.test(form.qty.trim()) || rate === null) {
      setMsg({
        kind: "error",
        text: "Pick a supplier and item, and enter quantity and rate as numbers.",
      });
      return;
    }
    try {
      const p = await api("/purchases", {
        method: "POST",
        token,
        body: {
          supplier_id: Number(form.supplier_id),
          purchase_date: localToday(),
          bill_no: form.bill_no.trim() || null,
          lines: [{ item_id: item.id, qty: form.qty.trim(), uom, rate_paise: rate }],
        },
      });
      setMsg({
        kind: "success",
        text: `Purchase #${p.id} posted: ${form.qty} ${uom} ${item.code}.`,
      });
      set({ qty: "", rate: "", bill_no: "" });
      onPosted?.();
    } catch (err) {
      setMsg({ kind: "error", text: err.message });
    }
  }

  return (
    <Card title="Record a purchase">
      <form onSubmit={save} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Supplier">
            <select
              className={input}
              value={form.supplier_id}
              onChange={(e) => set({ supplier_id: e.target.value })}
            >
              <option value="">Select…</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Item">
            <select
              className={input}
              value={form.item_id}
              onChange={(e) => set({ item_id: e.target.value })}
            >
              <option value="">Select…</option>
              {items.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label={`Quantity${uom ? ` (${uom})` : ""}`}>
            <input
              className={input}
              inputMode="decimal"
              value={form.qty}
              onChange={(e) => set({ qty: e.target.value })}
            />
          </Field>
          <Field label={`Rate (₹${uom ? `/${uom}` : ""}, before tax)`}>
            <input
              className={input}
              inputMode="decimal"
              value={form.rate}
              onChange={(e) => set({ rate: e.target.value })}
            />
          </Field>
          <Field label="Bill no (optional)">
            <input
              className={input}
              value={form.bill_no}
              onChange={(e) => set({ bill_no: e.target.value })}
            />
          </Field>
          {toPaise(form.rate) !== null && /^\d+$/.test(form.qty.trim()) && (
            <p className="self-end pb-2 text-sm text-slate-500">
              ≈ {inr(toPaise(form.rate) * Number(form.qty.trim()))} before tax
            </p>
          )}
        </div>
        {msg && <Banner kind={msg.kind}>{msg.text}</Banner>}
        <Button type="submit">Post purchase</Button>
      </form>
    </Card>
  );
}
