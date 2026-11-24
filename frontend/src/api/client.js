// One fetch wrapper for the whole app. Business rules live in the API; this just carries the JWT,
// sends/receives JSON, and turns the server's {error:{code,message,details}} into an ApiError.
const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message || code);
    this.status = status;
    this.code = code;
    this.details = details || {};
    this.offline = status === 0;
  }
}

export async function api(path, { method = "GET", body, token, headers = {} } = {}) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: {
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "NETWORK", "Network error — you may be offline");
  }
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err = (data && data.error) || {};
    throw new ApiError(res.status, err.code || `HTTP_${res.status}`, err.message, err.details);
  }
  return data;
}

// For auth-protected binary responses (the invoice PDF, CSV/XLSX exports): a plain link can't
// carry the JWT, so fetch the bytes with the token and hand back a Blob the caller can open/save.
export async function apiBlob(path, { token } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, `HTTP_${res.status}`, "download failed");
  return res.blob();
}
