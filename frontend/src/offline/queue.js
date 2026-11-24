// Minimal offline order queue (docs/architecture.md section 5). Each queued order gets a
// client_uuid, kept in localStorage; on flush it is POSTed with that uuid as the Idempotency-Key.
// Because the key is stable across retries, sending the same order twice lands exactly one order:
// the server replays the first result (sales.create_order). So the queue can retry freely.
//
// makeQueue takes its storage so it is testable without a browser.

const KEY = "ff.order.queue";

export function makeQueue(storage, key = KEY) {
  const read = () => {
    try {
      return JSON.parse(storage.getItem(key)) || [];
    } catch {
      return [];
    }
  };
  const write = (items) => storage.setItem(key, JSON.stringify(items));

  return {
    all: read,
    pending: () => read().filter((i) => i.state === "pending"),

    enqueue(body) {
      const items = read();
      const item = { client_uuid: crypto.randomUUID(), body, state: "pending" };
      items.push(item);
      write(items);
      return item;
    },

    // send(client_uuid, body) -> resolves with the order, or throws. A thrown error with
    // `.offline` leaves the item pending (retry later); any other error marks it failed (a 4xx
    // the same body can't fix, e.g. the customer isn't this salesman's).
    async flush(send) {
      const items = read();
      for (const item of items) {
        if (item.state !== "pending") continue;
        try {
          item.result = await send(item.client_uuid, item.body);
          item.state = "synced";
        } catch (err) {
          if (err && err.offline) break; // still offline: stop, keep the rest pending
          item.state = "failed";
          item.error = (err && err.message) || "failed";
        }
      }
      write(items);
      return read();
    },
  };
}
