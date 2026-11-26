import { useCallback, useEffect, useMemo, useState } from "react";

import { api, ApiError } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import ItemArt from "../components/SnackArt.jsx";
import { inr, toPaise } from "../format.js";
import { Banner, Button, Card, Field, input, Pill } from "../ui.jsx";

// Admin masters screen (P11): edit names, prices, GST rates, GSTINs, the salesman assigned to a
// customer, and whether any row is still active. The API is the source of truth for every rule;
// this page is a thin form.

const TABS = [
  ["items", "Items"],
  ["customers", "Customers"],
  ["suppliers", "Suppliers"],
];

export default function MastersPage() {
  const { auth } = useAuth();
  const token = auth.token;
  const [tab, setTab] = useState("items");
  const [showInactive, setShowInactive] = useState(false);
  const [rows, setRows] = useState([]);
  const [salesmen, setSalesmen] = useState([]);
  const [openId, setOpenId] = useState(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    setError("");
    setNote("");
    try {
      const path = `/${tab}?include_inactive=${showInactive}`;
      setRows(await api(path, { token }));
    } catch (e) {
      setError(e.message);
    }
  }, [tab, showInactive, token]);

  useEffect(() => {
    load();
  }, [load]);

  // Customers need the salesman list for the reassignment dropdown. Pulled from /customers once
  // (every customer carries a salesman_id of a user) by asking the user list directly isn't
  // exposed; using the server's known-salesmen set via the auth /users endpoint isn't either, so
  // we derive the list from the customers themselves — enough for a demo factory.
  useEffect(() => {
    if (tab !== "customers") return;
    (async () => {
      try {
        const all = await api("/customers?include_inactive=true", { token });
        const uniq = new Map();
        for (const c of all) if (c.salesman_id) uniq.set(c.salesman_id, c.salesman_id);
        setSalesmen([...uniq.values()]);
      } catch {
        /* non-fatal */
      }
    })();
  }, [tab, token]);

  const save = async (id, body) => {
    setError("");
    setNote("");
    try {
      await api(`/${tab}/${id}`, { method: "PATCH", token, body });
      setNote("Saved.");
      setOpenId(null);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  return (
    <>
      <div>
        <h1 className="text-3xl font-extrabold">Masters</h1>
        <p className="text-sm text-choc-500">
          Edit prices, tax rates, GSTINs and the salesman on a customer. Deactivated rows stay in
          the ledger: prior orders, invoices, lots and purchases keep their historical values.
        </p>
      </div>

      <nav className="-mx-1 flex flex-wrap gap-1 text-sm" aria-label="Masters">
        {TABS.map(([name, label]) => (
          <button
            key={name}
            type="button"
            onClick={() => {
              setTab(name);
              setOpenId(null);
            }}
            className={`whitespace-nowrap rounded-full px-3 py-1.5 font-medium ${
              tab === name ? "bg-turmeric-100 text-choc-900" : "text-choc-500 hover:text-choc-900"
            }`}
          >
            {label}
          </button>
        ))}
        <label className="ml-auto flex items-center gap-2 text-xs text-choc-500">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
          />
          Show inactive
        </label>
      </nav>

      <Banner>{error}</Banner>
      {note && <Banner kind="success">{note}</Banner>}

      <Card title={label(tab) + " (" + rows.length + ")"}>
        {rows.length === 0 ? (
          <p className="text-sm text-choc-500">Nothing to show.</p>
        ) : (
          <ul className="divide-y divide-line">
            {rows.map((row) => (
              <li key={row.id} className="py-3">
                <Row
                  tab={tab}
                  row={row}
                  open={openId === row.id}
                  onOpen={() => setOpenId(openId === row.id ? null : row.id)}
                  onSave={(body) => save(row.id, body)}
                  salesmen={salesmen}
                />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function label(tab) {
  const entry = TABS.find(([n]) => n === tab);
  return entry ? entry[1] : tab;
}

function Row({ tab, row, open, onOpen, onSave, salesmen }) {
  return (
    <>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-center justify-between gap-3 text-left"
      >
        <span className="flex items-center gap-3">
          {tab === "items" && <ItemArt code={row.code} name={row.name} className="h-8 w-8" />}
          <span>
            <span className="block font-semibold">{row.name}</span>
            <span className="text-xs text-choc-500">
              {row.code}
              {tab === "items" && ` · ${row.kind} · ${row.base_uom}`}
              {tab !== "items" && row.gstin && ` · ${row.gstin}`}
            </span>
          </span>
        </span>
        <span className="flex items-center gap-2 text-xs text-choc-500">
          {tab === "items" && row.kind === "FG" && row.sale_price_paise != null && (
            <span className="num">{inr(row.sale_price_paise)}</span>
          )}
          {tab !== "items" && row.state_code && <span>State {row.state_code}</span>}
          {row.is_active ? <Pill tone="ok">Active</Pill> : <Pill tone="muted">Inactive</Pill>}
        </span>
      </button>
      {open && (
        <div className="mt-3">
          {tab === "items" && <ItemForm row={row} onSave={onSave} />}
          {tab === "customers" && <CustomerForm row={row} onSave={onSave} salesmen={salesmen} />}
          {tab === "suppliers" && <PartyForm row={row} onSave={onSave} />}
        </div>
      )}
    </>
  );
}

function ItemForm({ row, onSave }) {
  const initial = useMemo(
    () => ({
      name: row.name,
      hsn: row.hsn || "",
      gst_pct: String(row.gst_rate_bp / 100),
      sale_price: row.sale_price_paise != null ? (row.sale_price_paise / 100).toFixed(2) : "",
      pack_size: row.pack_size || "",
      variance_tol_pct: String(row.variance_tol_bp / 100),
      shelf_life_days: row.shelf_life_days != null ? String(row.shelf_life_days) : "",
    }),
    [row],
  );
  const [v, setV] = useState(initial);

  const submit = () => {
    const body = {};
    if (v.name !== initial.name) body.name = v.name;
    if (v.hsn !== initial.hsn && v.hsn) body.hsn = v.hsn;
    const bp = Math.round(Number(v.gst_pct) * 100);
    if (bp !== row.gst_rate_bp) body.gst_rate_bp = bp;
    if (row.kind === "FG") {
      const p = toPaise(v.sale_price);
      if (p != null && p !== row.sale_price_paise) body.sale_price_paise = p;
    }
    if (v.pack_size !== initial.pack_size && v.pack_size) body.pack_size = v.pack_size;
    const tol = Math.round(Number(v.variance_tol_pct) * 100);
    if (tol !== row.variance_tol_bp) body.variance_tol_bp = tol;
    if (v.shelf_life_days !== initial.shelf_life_days && v.shelf_life_days) {
      body.shelf_life_days = Number(v.shelf_life_days);
    }
    onSave(body);
  };

  return (
    <div className="space-y-3 rounded-xl bg-cream p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <input
            className={input}
            value={v.name}
            onChange={(e) => setV({ ...v, name: e.target.value })}
          />
        </Field>
        <Field label="HSN">
          <input
            className={input}
            value={v.hsn}
            onChange={(e) => setV({ ...v, hsn: e.target.value })}
          />
        </Field>
        <Field label="GST (%)">
          <input
            className={input}
            value={v.gst_pct}
            onChange={(e) => setV({ ...v, gst_pct: e.target.value })}
          />
        </Field>
        {row.kind === "FG" && (
          <Field label="Sale price (₹)">
            <input
              className={input}
              value={v.sale_price}
              onChange={(e) => setV({ ...v, sale_price: e.target.value })}
            />
          </Field>
        )}
        <Field label="Pack size">
          <input
            className={input}
            value={v.pack_size}
            onChange={(e) => setV({ ...v, pack_size: e.target.value })}
          />
        </Field>
        <Field label="Variance tolerance (%)">
          <input
            className={input}
            value={v.variance_tol_pct}
            onChange={(e) => setV({ ...v, variance_tol_pct: e.target.value })}
          />
        </Field>
        <Field label="Shelf life (days)">
          <input
            className={input}
            value={v.shelf_life_days}
            onChange={(e) => setV({ ...v, shelf_life_days: e.target.value })}
          />
        </Field>
      </div>
      <ActionRow row={row} onSave={onSave} onSubmit={submit} />
    </div>
  );
}

function CustomerForm({ row, onSave, salesmen }) {
  const initial = useMemo(
    () => ({
      name: row.name,
      gstin: row.gstin || "",
      state_code: row.state_code || "",
      address: row.address || "",
      salesman_id: row.salesman_id != null ? String(row.salesman_id) : "",
    }),
    [row],
  );
  const [v, setV] = useState(initial);

  const submit = () => {
    const body = {};
    if (v.name !== initial.name) body.name = v.name;
    if (v.gstin !== initial.gstin) body.gstin = v.gstin || null;
    if (v.state_code !== initial.state_code && v.state_code) body.state_code = v.state_code;
    if (v.address !== initial.address) body.address = v.address || null;
    if (v.salesman_id !== initial.salesman_id)
      body.salesman_id = v.salesman_id ? Number(v.salesman_id) : null;
    onSave(body);
  };

  return (
    <div className="space-y-3 rounded-xl bg-cream p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <input
            className={input}
            value={v.name}
            onChange={(e) => setV({ ...v, name: e.target.value })}
          />
        </Field>
        <Field label="GSTIN">
          <input
            className={input}
            value={v.gstin}
            onChange={(e) => setV({ ...v, gstin: e.target.value })}
          />
        </Field>
        <Field label="State code">
          <input
            className={input}
            value={v.state_code}
            onChange={(e) => setV({ ...v, state_code: e.target.value })}
            maxLength={2}
          />
        </Field>
        <Field label="Salesman">
          <select
            className={input}
            value={v.salesman_id}
            onChange={(e) => setV({ ...v, salesman_id: e.target.value })}
          >
            <option value="">(none)</option>
            {salesmen.map((id) => (
              <option key={id} value={id}>
                Salesman #{id}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Address">
          <input
            className={input}
            value={v.address}
            onChange={(e) => setV({ ...v, address: e.target.value })}
          />
        </Field>
      </div>
      <ActionRow row={row} onSave={onSave} onSubmit={submit} />
    </div>
  );
}

function PartyForm({ row, onSave }) {
  const initial = useMemo(
    () => ({
      name: row.name,
      gstin: row.gstin || "",
      state_code: row.state_code || "",
    }),
    [row],
  );
  const [v, setV] = useState(initial);

  const submit = () => {
    const body = {};
    if (v.name !== initial.name) body.name = v.name;
    if (v.gstin !== initial.gstin) body.gstin = v.gstin || null;
    if (v.state_code !== initial.state_code && v.state_code) body.state_code = v.state_code;
    onSave(body);
  };

  return (
    <div className="space-y-3 rounded-xl bg-cream p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <input
            className={input}
            value={v.name}
            onChange={(e) => setV({ ...v, name: e.target.value })}
          />
        </Field>
        <Field label="GSTIN">
          <input
            className={input}
            value={v.gstin}
            onChange={(e) => setV({ ...v, gstin: e.target.value })}
          />
        </Field>
        <Field label="State code">
          <input
            className={input}
            value={v.state_code}
            onChange={(e) => setV({ ...v, state_code: e.target.value })}
            maxLength={2}
          />
        </Field>
      </div>
      <ActionRow row={row} onSave={onSave} onSubmit={submit} />
    </div>
  );
}

function ActionRow({ row, onSave, onSubmit }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <Button
        variant={row.is_active ? "danger" : "ghost"}
        onClick={() => onSave({ is_active: !row.is_active })}
      >
        {row.is_active ? "Deactivate" : "Reactivate"}
      </Button>
      <Button onClick={onSubmit}>Save changes</Button>
    </div>
  );
}
