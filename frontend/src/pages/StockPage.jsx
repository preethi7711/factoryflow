import { useCallback, useEffect, useState } from "react";

import { api, apiBlob } from "../api/client.js";
import { useAuth } from "../auth/AuthContext.jsx";
import ItemArt from "../components/SnackArt.jsx";
import { DISPLAY_UNIT, inr, localToday, showQty } from "../format.js";
import { Banner, Button, Card, Field, input } from "../ui.jsx";

function monthDefaults() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  const iso = (d) => localToday(d);
  return [iso(first), iso(last)];
}

// Report cells arrive exactly as the ledger stores them (base units, paise). Show kg / l and rupees;
// the downloads keep the raw values so an auditor can re-add them.
function cell(key, row) {
  const v = row[key];
  if (v == null) return "";
  if (key.endsWith("_paise")) return inr(Number(v));
  if (key.endsWith("_qty")) return showQty(v, row.uom).split(" ")[0];
  if (key === "uom") return (DISPLAY_UNIT[v] || [v])[0];
  return v;
}
const label = (text) => text.replace(" (paise)", "");
const isNumber = (key) => key.endsWith("_qty") || key.endsWith("_paise");

const REPORTS = [
  ["sales-register", "Sales register"],
  ["stock-summary", "Stock summary"],
  ["stock-ledger", "Stock ledger"],
  ["production", "Production"],
];

export default function StockPage() {
  const { auth } = useAuth();
  const token = auth.token;
  const [[from, to], setRange] = useState(monthDefaults);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setSummary(await api(`/reports/stock-summary?from=${from}&to=${to}`, { token }));
    } catch (e) {
      setError(e.message);
    }
  }, [token, from, to]);

  useEffect(() => {
    load();
  }, [load]);

  async function download(name, format) {
    const blob = await apiBlob(`/reports/${name}?from=${from}&to=${to}&format=${format}`, {
      token,
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${name}_${from}_${to}.${format}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div>
        <h1 className="text-3xl font-extrabold">Stock &amp; reports</h1>
        <p className="text-sm text-choc-500">
          Every figure is read from the stock ledger for the period you pick. Read-only.
        </p>
      </div>

      <Card title="Period">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="From">
            <input
              className={input}
              type="date"
              value={from}
              onChange={(e) => setRange([e.target.value, to])}
            />
          </Field>
          <Field label="To">
            <input
              className={input}
              type="date"
              value={to}
              onChange={(e) => setRange([from, e.target.value])}
            />
          </Field>
          <Button onClick={load}>Refresh</Button>
        </div>
      </Card>

      <Banner>{error}</Banner>

      {summary && (
        <Card title="Stock summary">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left text-choc-500">
                  {summary.columns.map((c) => (
                    <th
                      key={c.key}
                      className={`py-2 pr-3 font-medium ${isNumber(c.key) ? "text-right" : ""}`}
                    >
                      {label(c.label)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {summary.rows.map((row, i) => (
                  <tr key={i} className="border-b border-line">
                    {summary.columns.map((c) => (
                      <td
                        key={c.key}
                        className={`py-2 pr-3 ${isNumber(c.key) ? "num text-right" : ""}`}
                      >
                        {c.key === "item_code" ? (
                          <span className="flex items-center gap-2 font-medium">
                            <ItemArt code={row.item_code} className="h-7 w-7" />
                            {row.item_code}
                          </span>
                        ) : (
                          cell(c.key, row)
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card title="Download">
        <div className="space-y-2 text-sm">
          {REPORTS.map(([name, label]) => (
            <div key={name} className="flex items-center justify-between">
              <span>{label}</span>
              <div className="flex gap-2">
                <Button variant="ghost" onClick={() => download(name, "csv")}>
                  CSV
                </Button>
                <Button variant="ghost" onClick={() => download(name, "xlsx")}>
                  XLSX
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
