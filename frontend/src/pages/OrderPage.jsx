import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import { inr } from "../format.js";
import { makeQueue } from "../offline/queue.js";
import { Banner, Button, Card, Field, input } from "../ui.jsx";

const today = () => new Date().toISOString().slice(0, 10);

export default function OrderPage() {
  const { auth } = useAuth();
  const token = auth.token;
  const queue = useMemo(() => makeQueue(window.localStorage), []);

  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [customerId, setCustomerId] = useState("");
  const [lines, setLines] = useState([{ item_id: "", qty: "" }]);
  const [items, setItems] = useState(queue.all());
  const [online, setOnline] = useState(navigator.onLine);
  const [msg, setMsg] = useState(null);

  const send = useCallback(
    (key, body) =>
      api("/orders", { method: "POST", body, token, headers: { "Idempotency-Key": key } }),
    [token],
  );

  const flush = useCallback(async () => {
    setItems(await queue.flush(send));
  }, [queue, send]);

  // Load the price list and (own) customers; re-price and re-send any orders queued offline.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [me, custs, prices] = await Promise.all([
          api("/auth/me", { token }),
          api("/customers", { token }),
          api("/price-list", { token }),
        ]);
        if (!alive) return;
        const mine = custs.filter((c) => c.salesman_id == null || c.salesman_id === me.id);
        setCustomers(mine.length ? mine : custs);
        setProducts(prices);
      } catch {
        /* offline: the queue still works; masters load on reconnect */
      }
    })();
    return () => {
      alive = false;
    };
  }, [token]);

  useEffect(() => {
    flush();
    const on = () => {
      setOnline(true);
      flush();
    };
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, [flush]);

  function setLine(i, patch) {
    setLines((ls) => ls.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  }

  function placeOrder(e) {
    e.preventDefault();
    const body = {
      customer_id: Number(customerId),
      order_date: today(),
      lines: lines
        .filter((l) => l.item_id && l.qty)
        .map((l) => ({ item_id: Number(l.item_id), qty: String(l.qty), uom: "pkt" })),
    };
    if (!body.customer_id || body.lines.length === 0) {
      setMsg({ kind: "error", text: "Pick a customer and at least one product." });
      return;
    }
    queue.enqueue(body);
    setItems(queue.all());
    setCustomerId("");
    setLines([{ item_id: "", qty: "" }]);
    setMsg({ kind: "success", text: "Order queued. It syncs when you're online." });
    flush();
  }

  const pending = items.filter((i) => i.state === "pending").length;
  const productName = (id) => products.find((p) => p.item_id === id)?.name || `item ${id}`;

  return (
    <>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">New order</h1>
        <span className={`text-sm ${online ? "text-emerald-600" : "text-amber-600"}`}>
          {online ? "online" : "offline"} · {pending} pending
        </span>
      </div>

      <Card title="Place an order">
        <form onSubmit={placeOrder} className="space-y-3">
          <Field label="Customer">
            <select
              className={input}
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
            >
              <option value="">Select a customer…</option>
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.code})
                </option>
              ))}
            </select>
          </Field>

          {lines.map((line, i) => (
            <div key={i} className="flex gap-2">
              <select
                className={input}
                value={line.item_id}
                onChange={(e) => setLine(i, { item_id: e.target.value })}
              >
                <option value="">Product…</option>
                {products.map((p) => (
                  <option key={p.item_id} value={p.item_id}>
                    {p.name} — {inr(p.sale_price_paise)}
                  </option>
                ))}
              </select>
              <input
                className={`${input} w-28`}
                inputMode="decimal"
                placeholder="qty (pkt)"
                value={line.qty}
                onChange={(e) => setLine(i, { qty: e.target.value })}
              />
              {lines.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setLines((ls) => ls.filter((_, j) => j !== i))}
                >
                  ×
                </Button>
              )}
            </div>
          ))}

          <Button
            type="button"
            variant="ghost"
            onClick={() => setLines((ls) => [...ls, { item_id: "", qty: "" }])}
          >
            + Add product
          </Button>

          {msg && <Banner kind={msg.kind}>{msg.text}</Banner>}
          <Button type="submit" className="w-full">
            Place order
          </Button>
        </form>
      </Card>

      <Card
        title="Queued orders"
        actions={
          <Button variant="ghost" onClick={flush}>
            Sync now
          </Button>
        }
      >
        {items.length === 0 ? (
          <p className="text-sm text-slate-500">No orders yet.</p>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {[...items].reverse().map((item) => (
              <li key={item.client_uuid} className="flex items-center justify-between py-2">
                <span>
                  {item.body.lines.map((l) => `${l.qty} × ${productName(l.item_id)}`).join(", ") ||
                    "order"}
                </span>
                <State item={item} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

function State({ item }) {
  if (item.state === "synced") {
    return <span className="text-emerald-600">synced · #{item.result?.id}</span>;
  }
  if (item.state === "failed") {
    return <span className="text-rose-600">failed · {item.error}</span>;
  }
  return <span className="text-amber-600">pending</span>;
}
