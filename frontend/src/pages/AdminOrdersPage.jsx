import { useCallback, useEffect, useState } from "react";

import { api, apiBlob } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { inr, localToday } from "../format.js";
import { Banner, Button, Card } from "../ui.jsx";

const today = () => localToday();

export default function AdminOrdersPage() {
  const { auth } = useAuth();
  const token = auth.token;
  const [orders, setOrders] = useState([]);
  const [invoices, setInvoices] = useState({}); // orderId -> invoice (kept for this session)
  const [msg, setMsg] = useState({}); // orderId -> {kind, text}
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setOrders(await api("/orders", { token }));
    } catch (err) {
      setError(err.message);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const note = (id, kind, text) => setMsg((m) => ({ ...m, [id]: { kind, text } }));

  async function act(id, fn) {
    try {
      await fn();
      await load();
    } catch (err) {
      if (err.code === "INSUFFICIENT_STOCK") {
        const d = err.details;
        note(id, "error", `Short by ${d.shortage} (want ${d.requested}, have ${d.available}).`);
      } else {
        note(id, "error", err.message);
      }
    }
  }

  const approve = (o) => act(o.id, () => api(`/orders/${o.id}/approve`, { method: "POST", token }));

  const invoice = (o) =>
    act(o.id, async () => {
      const inv = await api(`/orders/${o.id}/invoice`, {
        method: "POST",
        token,
        body: { invoice_date: today() },
      });
      setInvoices((m) => ({ ...m, [o.id]: inv }));
      note(o.id, "success", `Invoice ${inv.invoice_no} raised.`);
    });

  const dispatch = (o) =>
    act(o.id, () =>
      api(`/invoices/${invoices[o.id].id}/dispatch`, {
        method: "POST",
        token,
        body: { dispatch_date: today() },
      }),
    );

  const pay = (o) =>
    act(o.id, async () => {
      const inv = invoices[o.id];
      await api("/payments", {
        method: "POST",
        token,
        body: {
          customer_id: o.customer_id,
          payment_date: today(),
          amount_paise: inv.total_paise,
          allocations: [{ invoice_id: inv.id, amount_paise: inv.total_paise }],
        },
      });
      note(o.id, "success", `Recorded ${inr(inv.total_paise)} against ${inv.invoice_no}.`);
    });

  async function viewPdf(o) {
    const blob = await apiBlob(`/invoices/${invoices[o.id].id}/pdf`, { token });
    window.open(URL.createObjectURL(blob), "_blank");
  }

  return (
    <>
      <h1 className="text-xl font-semibold">Orders</h1>
      <Banner>{error}</Banner>
      {orders.length === 0 && <p className="text-sm text-slate-500">No orders yet.</p>}
      {orders.map((o) => {
        const inv = invoices[o.id];
        return (
          <Card
            key={o.id}
            title={`${o.customer_code} · order #${o.id}`}
            actions={<Status s={o.status} />}
          >
            <ul className="mb-3 text-sm text-slate-600">
              {o.lines.map((l) => (
                <li key={l.id}>
                  {l.qty} × {l.item_code} — {inr(l.taxable_paise)}
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-2">
              {o.status === "PENDING" && <Button onClick={() => approve(o)}>Approve</Button>}
              {o.status === "APPROVED" && <Button onClick={() => invoice(o)}>Raise invoice</Button>}
              {o.status === "INVOICED" && inv && (
                <>
                  <Button onClick={() => dispatch(o)}>Dispatch</Button>
                  <Button variant="ghost" onClick={() => viewPdf(o)}>
                    View invoice PDF
                  </Button>
                </>
              )}
              {o.status === "DISPATCHED" && inv && (
                <>
                  <Button onClick={() => pay(o)}>Record payment ({inr(inv.total_paise)})</Button>
                  <Button variant="ghost" onClick={() => viewPdf(o)}>
                    View invoice PDF
                  </Button>
                </>
              )}
              {o.status === "INVOICED" && !inv && (
                <span className="text-sm text-slate-500">
                  Invoiced earlier — reopen from this session to dispatch.
                </span>
              )}
            </div>
            {msg[o.id] && (
              <div className="mt-3">
                <Banner kind={msg[o.id].kind}>{msg[o.id].text}</Banner>
              </div>
            )}
          </Card>
        );
      })}
    </>
  );
}

function Status({ s }) {
  const color =
    {
      PENDING: "bg-amber-100 text-amber-800",
      APPROVED: "bg-sky-100 text-sky-800",
      INVOICED: "bg-indigo-100 text-indigo-800",
      DISPATCHED: "bg-emerald-100 text-emerald-800",
      CANCELLED: "bg-slate-200 text-slate-600",
    }[s] || "bg-slate-100 text-slate-700";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>{s}</span>;
}
