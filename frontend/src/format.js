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
