import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import ItemArt from "../components/SnackArt.jsx";
import { inr, localToday } from "../format.js";
import { makeQueue } from "../offline/queue.js";
import { Banner, Button, Card, Pill } from "../ui.jsx";

// Salesman order screen (spec M3, PROBLEM.md 4.1). Same flow as before: pick a customer, set packet
// counts, place the order. Placing always goes through the offline queue: the order is saved on the
// phone first, then sent with its client_uuid as the Idempotency-Key, so a retry can never duplicate it.
// Prices shown here are the factory price list; the server re-prices every line when the order arrives.

// GST state codes -> names (a fixed government code list, not business data).
const STATE = {
  29: "Karnataka",
  32: "Kerala",
  33: "Tamil Nadu",
  34: "Puducherry",
  36: "Telangana",
  37: "Andhra Pradesh",
};
const STEPS = ["PENDING", "APPROVED", "INVOICED", "DISPATCHED"];
const STEP_NAME = {
  PENDING: "Placed",
  APPROVED: "Approved",
  INVOICED: "Invoiced",
  DISPATCHED: "Dispatched",
};

export default function OrderPage() {
  const { auth } = useAuth();
  const token = auth.token;
  // One queue per salesman, so a shared phone (or the demo browser) never sends A's order as B.
  const queue = useMemo(
    () => makeQueue(window.localStorage, `ff.order.queue.${auth.username}`),
    [auth.username],
  );

  const [customers, setCustomers] = useState([]);
  const [products, setProducts] = useState([]);
  const [orders, setOrders] = useState([]); // this salesman's orders, from the server
  const [fullName, setFullName] = useState("");
  const [customerId, setCustomerId] = useState(null);
  const [qty, setQty] = useState({}); // item_id -> whole packets
  const [items, setItems] = useState(queue.all()); // the local queue
  const [online, setOnline] = useState(navigator.onLine);
  const [msg, setMsg] = useState(null);

  const send = useCallback(
    (key, body) =>
      api("/orders", { method: "POST", body, token, headers: { "Idempotency-Key": key } }),
    [token],
  );

  const loadOrders = useCallback(() => {
    api("/orders", { token })
      .then(setOrders)
      .catch(() => {}); // offline: keep what we have
  }, [token]);

  const flush = useCallback(async () => {
    setItems(await queue.flush(send));
    loadOrders();
  }, [queue, send, loadOrders]);

  // Load the price list and (own) customers; re-send any orders queued offline.
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
        const list = mine.length ? mine : custs;
        setFullName(me.full_name);
        setCustomers(list);
        if (list.length === 1) setCustomerId(list[0].id); // one customer: nothing to choose
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

  const count = (id) => qty[id] || 0;
  const setCount = (id, n) => setQty((q) => ({ ...q, [id]: Math.max(0, n) }));
  const chosen = products.filter((p) => count(p.item_id) > 0);
  const packets = chosen.reduce((sum, p) => sum + count(p.item_id), 0);
  // Whole packets × integer paise is an exact integer: an estimate before GST, re-priced by the server.
  const estimate = chosen.reduce((sum, p) => sum + count(p.item_id) * p.sale_price_paise, 0);

  function placeOrder() {
    if (!customerId || chosen.length === 0) {
      setMsg({ kind: "error", text: "Pick a customer and add at least one product." });
      return;
    }
    queue.enqueue({
      customer_id: customerId,
      order_date: localToday(),
      lines: chosen.map((p) => ({
        item_id: p.item_id,
        qty: String(count(p.item_id)),
        uom: "pkt",
      })),
    });
    setItems(queue.all());
    setQty({});
    setMsg({
      kind: "success",
      text: online
        ? "Order placed. Sending it to the factory."
        : "Saved on this phone. It sends when you're back online.",
    });
    flush();
  }

  const pending = items.filter((i) => i.state === "pending").length;
  const productName = (id) => products.find((p) => p.item_id === id)?.name || `item ${id}`;
  const customerName = (code) => customers.find((c) => c.code === code)?.name || code;

  // Customer-wise sales: what this salesman has ordered per customer (before GST), from the server.
  const byCustomer = Object.entries(
    orders
      .filter((o) => o.status !== "REJECTED" && o.status !== "CANCELLED")
      .reduce(
        (acc, o) => ({ ...acc, [o.customer_code]: (acc[o.customer_code] || 0) + o.taxable_paise }),
        {},
      ),
  );

  return (
    <div className="space-y-4 pb-28">
      <Welcome name={fullName || auth.username} online={online} pending={pending} />

      <Card title="Ordering for">
        {customers.length === 0 ? (
          <p className="text-sm text-choc-500">
            {online ? "Loading customers…" : "Customers load when you're online."}
          </p>
        ) : (
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Customer">
            {customers.map((c) => {
              const on = c.id === customerId;
              return (
                <button
                  key={c.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => setCustomerId(c.id)}
                  className={`min-h-[44px] rounded-2xl border px-4 py-2 text-left text-sm ${
                    on
                      ? "border-choc-900 bg-choc-900 text-cream"
                      : "border-line bg-paper hover:border-choc-300"
                  }`}
                >
                  <span className="block font-semibold">{c.name}</span>
                  <span className={on ? "text-turmeric-100" : "text-choc-500"}>
                    {STATE[c.state_code] || `State ${c.state_code}`}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </Card>

      <section aria-labelledby="price-list">
        <h2 id="price-list" className="mb-2 text-lg font-semibold">
          Price list
        </h2>
        {products.length === 0 && <p className="text-sm text-choc-500">No products loaded yet.</p>}
        <div className={`grid gap-3 ${products.length === 1 ? "grid-cols-1" : "grid-cols-2"}`}>
          {products.map((p) => (
            <ProductCard
              key={p.item_id}
              product={p}
              count={count(p.item_id)}
              onChange={(n) => setCount(p.item_id, n)}
            />
          ))}
        </div>
      </section>

      {msg && <Banner kind={msg.kind}>{msg.text}</Banner>}

      <Card
        title="My orders"
        actions={
          <Button variant="ghost" onClick={flush} className="min-h-[36px] px-3 py-1">
            Sync now
          </Button>
        }
      >
        <QueueList items={items} productName={productName} />
        <ul className="space-y-2">
          {[...orders]
            .reverse()
            .slice(0, 6)
            .map((o) => (
              <li key={o.id} className="rounded-xl bg-cream px-3 py-2">
                <div className="flex items-baseline justify-between gap-2 text-sm">
                  <span className="font-semibold">
                    #{o.id} {customerName(o.customer_code)}
                  </span>
                  <span className="num text-choc-500">{inr(o.taxable_paise)}</span>
                </div>
                <Timeline status={o.status} />
              </li>
            ))}
        </ul>
        {orders.length === 0 && items.length === 0 && (
          <p className="text-sm text-choc-500">No orders yet. Your first one shows up here.</p>
        )}
      </Card>

      {byCustomer.length > 0 && (
        <Card title="Sales by customer">
          <dl className="space-y-1 text-sm">
            {byCustomer.map(([code, paise]) => (
              <div key={code} className="flex justify-between">
                <dt>{customerName(code)}</dt>
                <dd className="num font-semibold">{inr(paise)}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-2 text-xs text-choc-500">
            Orders placed, before GST. Rejected and cancelled orders are left out.
          </p>
        </Card>
      )}

      <OrderBar
        packets={packets}
        estimate={estimate}
        ready={Boolean(customerId) && packets > 0}
        onPlace={placeOrder}
      />
    </div>
  );
}

function Welcome({ name, online, pending }) {
  return (
    <div className="relative overflow-hidden rounded-2xl bg-turmeric-500 px-4 py-4 text-choc-900">
      <div className="kolam absolute inset-0 opacity-40" aria-hidden="true" />
      <div className="relative flex items-center justify-between gap-3">
        <div>
          <p className="font-display text-2xl font-extrabold leading-tight">Vanakkam, {name}</p>
          <p className="text-sm">Pick a customer, tap in packets, place the order.</p>
        </div>
        <ItemArt code="MURUKKU" className="h-16 w-16 shrink-0 motion-safe:animate-spin-slow" />
      </div>
      <div className="relative mt-3 flex flex-wrap gap-2">
        <Pill tone={online ? "ok" : "bad"}>
          {online ? "Online" : "Offline: orders save on this phone"}
        </Pill>
        {pending > 0 && <Pill tone="wait">{pending} waiting to send</Pill>}
      </div>
    </div>
  );
}

function ProductCard({ product: p, count, onChange }) {
  const picked = count > 0;
  return (
    <article
      className={`flex flex-col rounded-2xl border p-3 transition-colors ${
        picked ? "border-turmeric-700 bg-turmeric-50" : "border-line bg-paper"
      }`}
    >
      <div className="flex justify-center rounded-xl bg-cream py-3">
        <ItemArt code={p.code} name={p.name} className="h-20 w-20" />
      </div>
      <h3 className="mt-2 text-base font-semibold leading-tight">{p.name}</h3>
      <p className="text-xs text-choc-500">
        <span className="num">{inr(p.sale_price_paise)}</span> per {p.uom} + {p.gst_rate_bp / 100}%
        GST
      </p>
      <div className="mt-auto flex items-center justify-between gap-1 pt-3">
        <StepButton
          label={`One less ${p.name}`}
          onClick={() => onChange(count - 1)}
          disabled={!picked}
        >
          −
        </StepButton>
        <input
          aria-label={`${p.name} packets`}
          inputMode="numeric"
          value={picked ? count : ""}
          placeholder="0"
          onChange={(e) => onChange(Number(e.target.value.replace(/\D/g, "")) || 0)}
          className="num w-14 rounded-lg border border-line bg-paper py-2 text-center text-base font-semibold"
        />
        <StepButton label={`One more ${p.name}`} onClick={() => onChange(count + 1)}>
          +
        </StepButton>
      </div>
      <button
        type="button"
        onClick={() => onChange(count + 10)}
        className="mt-2 min-h-[36px] rounded-full text-xs font-semibold text-turmeric-700 hover:underline"
      >
        +10 packets
      </button>
    </article>
  );
}

function StepButton({ label, children, ...props }) {
  return (
    <button
      type="button"
      aria-label={label}
      className="h-11 w-11 rounded-full bg-choc-900 text-xl font-bold text-cream active:scale-95 disabled:opacity-30"
      {...props}
    >
      {children}
    </button>
  );
}

// Sticky at the bottom, within thumb reach. The packet count pops each time it changes.
function OrderBar({ packets, estimate, ready, onPlace }) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-10 px-3 pb-3">
      <div className="mx-auto flex max-w-lg items-center justify-between gap-3 rounded-2xl bg-choc-900 px-4 py-3 text-cream shadow-lg">
        <div className="leading-tight">
          <p key={packets} className="num animate-pop font-display text-xl font-extrabold">
            {packets} {packets === 1 ? "packet" : "packets"}
          </p>
          <p className="num text-xs text-choc-100">{inr(estimate)} before GST</p>
        </div>
        <Button variant="accent" onClick={onPlace} disabled={!ready}>
          Place order
        </Button>
      </div>
    </div>
  );
}

// Orders still on the phone (not yet accepted by the server).
function QueueList({ items, productName }) {
  const open = items.filter((i) => i.state !== "synced");
  if (open.length === 0) return null;
  return (
    <ul className="mb-2 space-y-1 text-sm">
      {open.map((item) => (
        <li
          key={item.client_uuid}
          className="flex items-center justify-between gap-2 rounded-xl border border-dashed border-choc-300 px-3 py-2"
        >
          <span>
            {item.body.lines.map((l) => `${l.qty} × ${productName(l.item_id)}`).join(", ")}
          </span>
          {item.state === "failed" ? (
            <Pill tone="bad">Not sent: {item.error}</Pill>
          ) : (
            <Pill tone="wait">On this phone</Pill>
          )}
        </li>
      ))}
    </ul>
  );
}

// Placed → Approved → Invoiced → Dispatched, read from the order's real status.
function Timeline({ status }) {
  if (status === "REJECTED" || status === "CANCELLED") {
    return (
      <p className="mt-1 text-xs font-semibold text-chilli-700">
        {status === "REJECTED" ? "Rejected" : "Cancelled"}
      </p>
    );
  }
  const reached = STEPS.indexOf(status);
  return (
    <ol
      className="mt-2 flex items-center gap-1"
      aria-label={`Status: ${STEP_NAME[status] || status}`}
    >
      {STEPS.map((s, i) => (
        <li key={s} className="flex flex-1 flex-col items-center gap-1">
          <span
            className={`h-1.5 w-full rounded-full ${i <= reached ? "bg-leaf-500" : "bg-line"}`}
          />
          <span
            className={`text-[11px] ${i <= reached ? "font-semibold text-leaf-700" : "text-choc-500"}`}
          >
            {STEP_NAME[s]}
          </span>
        </li>
      ))}
    </ol>
  );
}
