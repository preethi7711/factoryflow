// Mirror of backend core.money.format_inr: paise -> "₹1,23,456.78" (Indian digit grouping).
export function inr(paise) {
  const sign = paise < 0 ? "-" : "";
  const abs = Math.abs(paise);
  const rupees = Math.floor(abs / 100);
  const rem = abs % 100;
  const digits = String(rupees);
  const head = digits.slice(0, -3);
  const tail = digits.slice(-3);
  const groups = [];
  let rest = head;
  while (rest.length > 2) {
    groups.unshift(rest.slice(-2));
    rest = rest.slice(0, -2);
  }
  if (rest) groups.unshift(rest);
  const grouped = [...groups, tail].filter(Boolean).join(",");
  return `${sign}₹${grouped}.${String(rem).padStart(2, "0")}`;
}

// Today's date in the browser's local zone (IST for the factory). toISOString() would give the
// UTC date, which is still "yesterday" between midnight and 05:30 IST.
export function localToday(d = new Date()) {
  const two = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`;
}

// "1200", "1,200.5" or "₹1200.50" -> integer paise, parsed from the text (never through a float).
// Returns null when the text isn't a valid rupee amount with at most two decimals.
export function toPaise(text) {
  const clean = String(text).replace(/[,₹\s]/g, "");
  const m = /^(\d+)(?:\.(\d{1,2}))?$/.exec(clean);
  if (!m) return null;
  return Number(m[1]) * 100 + Number((m[2] || "").padEnd(2, "0"));
}

// Exact decimal multiply on strings ("1.2" x "3" = "3.6"), using BigInt so 1.2 * 3 never
// becomes 3.5999999999999996. Quantities go to the API as strings, so they must be exact.
export function decMul(a, b) {
  const parse = (s) => {
    const [int, frac = ""] = String(s).split(".");
    return { digits: BigInt(int + frac), scale: frac.length };
  };
  const x = parse(a);
  const y = parse(b);
  const scale = x.scale + y.scale;
  const raw = (x.digits * y.digits).toString().padStart(scale + 1, "0");
  const int = raw.slice(0, raw.length - scale);
  const frac = raw.slice(raw.length - scale).replace(/0+$/, "");
  return frac ? `${int}.${frac}` : int;
}

// Base units are g / ml (exact storage); people think in kg / l. Display factor per base unit.
export const DISPLAY_UNIT = { g: ["kg", "0.001"], ml: ["l", "0.001"] };

// "10500.000" ml -> "10.5 l", "194.000" pcs -> "194 pcs". Exact string maths; for display only.
export function showQty(qty, uom) {
  const [unit, factor] = DISPLAY_UNIT[uom] || [uom, "1"];
  return `${decMul(qty, factor)} ${unit}`;
}
