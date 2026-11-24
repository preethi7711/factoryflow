import { useCallback, useEffect, useState } from "react";

import { api, apiBlob } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { inr, localToday, toPaise } from "../format.js";
import { Banner, Button, Card, input } from "../ui.jsx";

const today = () => localToday();

// "₹7,500.00 taxable + ₹187.50 CGST + ₹187.50 SGST = ₹7,875.00" (or IGST for another state).
// Every figure comes from the server's invoice or tax preview; nothing is recomputed here.
function taxLine(t) {
  const tax =
    t.supply_type === "INTER"
      ? `${inr(t.igst_paise)} IGST`
      : `${inr(t.cgst_paise)} CGST + ${inr(t.sgst_paise)} SGST`;
  return `${inr(t.taxable_paise)} taxable + ${tax} = ${inr(t.total_paise)}`;
}

export default function AdminOrdersPage() {
  const { auth } = useAuth();
  const token = auth.token;
  const [orders, setOrders] = useState([]);
  const [invoices, setInvoices] = useState({}); // orderId -> invoice (kept for this session)
  const [msg, setMsg] = useState({}); // orderId -> {kind, text}
  const [payAmount, setPayAmount] = useState({}); // orderId -> rupees typed
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
        // Benchmark step 6: show the shortage, and what the tax would be if it were invoiced
        // (GET /orders/{id}/tax-preview computes it server-side without creating anything).
        const d = err.details;
        const preview = await api(`/orders/${id}/tax-preview`, { token }).catch(() => null);
        note(
          id,
          "error",
          `Short by ${Number(d.shortage)} (want ${Number(d.requested)}, have ${Number(d.available)}).` +
            (preview ? ` If invoiced: ${taxLine(preview)}.` : ""),
        );
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
      note(o.id, "success", `Invoice ${inv.invoice_no} raised: ${taxLine(inv)}.`);
    });

  const dispatch = (o) =>
    act(o.id, () =>
      api(`/invoices/${invoices[o.id].id}/dispatch`, {
        method: "POST",
        token,
        body: { dispatch_date: today() },
      }),
    );

  // Benchmark step 7: a part payment (₹4,000 of ₹7,875). The amount is typed in rupees and parsed
  // to paise from the text; the outstanding shown afterwards comes from the server, not from here.
  const pay = (o) =>
    act(o.id, async () => {
      const inv = invoices[o.id];
      const amount = toPaise(payAmount[o.id] ?? "");
      if (!amount) throw new Error("Enter the amount received in rupees, e.g. 4000.");
      await api("/payments", {
        method: "POST",
        token,
        body: {
          customer_id: o.customer_id,
          payment_date: today(),
          amount_paise: amount,
          allocations: [{ invoice_id: inv.id, amount_paise: amount }],
        },
      });
      const out = await api(`/customers/${o.customer_id}/outstanding`, { token });
      setPayAmount((m) => ({ ...m, [o.id]: "" }));
      note(
        o.id,
        "success",
        `Recorded ${inr(amount)} against ${inv.invoice_no}. ${o.customer_code} outstanding: ${inr(out.outstanding_paise)}.`,
      );
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
                  {Number(l.qty)} × {l.item_code} — {inr(l.taxable_paise)}
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
                  <input
                    aria-label={`Amount received for ${inv.invoice_no} (₹)`}
                    className={`${input} w-32`}
                    inputMode="decimal"
                    placeholder={`₹ of ${inr(inv.total_paise)}`}
                    value={payAmount[o.id] ?? ""}
                    onChange={(e) => setPayAmount((m) => ({ ...m, [o.id]: e.target.value }))}
                  />
                  <Button onClick={() => pay(o)}>Record payment</Button>
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
