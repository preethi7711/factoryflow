// Remembers small ids across reloads and logins (which run, which invoice). The server stays the source
// of truth: pages re-read the document by id, and forget the id if the server no longer returns it.
export function remember(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode or storage full: the page still works, it just forgets on reload */
  }
}

export function recall(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw == null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}
