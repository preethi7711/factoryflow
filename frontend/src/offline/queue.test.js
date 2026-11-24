import { describe, expect, it } from "vitest";

import { makeQueue } from "./queue.js";

function fakeStorage() {
  const map = new Map();
  return {
    getItem: (k) => (map.has(k) ? map.get(k) : null),
    setItem: (k, v) => map.set(k, v),
  };
}

// A stand-in for the server's idempotent create: the first time a key is seen it "creates" an
// order; the same key again replays that same order (sales.create_order behaviour).
function fakeServer() {
  const byKey = new Map();
  let nextId = 1;
  return {
    created: () => [...byKey.values()],
    send: async (key, body) => {
      if (byKey.has(key)) return byKey.get(key);
      const order = { id: nextId++, ...body };
      byKey.set(key, order);
      return order;
    },
  };
}

describe("offline order queue", () => {
  it("flushes a queued order once and marks it synced", async () => {
    const q = makeQueue(fakeStorage());
    q.enqueue({ customer_id: 1, lines: [{ item_id: 9, qty: "10" }] });
    const server = fakeServer();
    await q.flush(server.send);
    expect(server.created()).toHaveLength(1);
    expect(q.pending()).toHaveLength(0);
  });

  it("a queued order resent with the same key lands exactly once", async () => {
    const q = makeQueue(fakeStorage());
    q.enqueue({ customer_id: 1, lines: [{ item_id: 9, qty: "10" }] });
    const server = fakeServer();

    // First attempt: the server commits the order but the reply is lost, so we see a network error
    // and the item stays pending (the honest double-send a flaky connection causes).
    const lossy = async (key, body) => {
      await server.send(key, body);
      const err = new Error("connection dropped");
      err.offline = true;
      throw err;
    };
    await q.flush(lossy);
    expect(q.pending()).toHaveLength(1);

    // Retry with the same client_uuid: the server replays, so there is still ONE order.
    await q.flush(server.send);
    expect(server.created()).toHaveLength(1);
    expect(q.pending()).toHaveLength(0);
  });

  it("stops flushing when still offline, keeping orders pending", async () => {
    const q = makeQueue(fakeStorage());
    q.enqueue({ customer_id: 1, lines: [] });
    q.enqueue({ customer_id: 2, lines: [] });
    const offline = async () => {
      const err = new Error("offline");
      err.offline = true;
      throw err;
    };
    await q.flush(offline);
    expect(q.pending()).toHaveLength(2);
  });
});
