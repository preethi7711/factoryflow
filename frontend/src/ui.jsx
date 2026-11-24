// A few shared bits so the pages stay short. Tailwind classes only.

export function Button({ className = "", variant = "primary", ...props }) {
  const styles = {
    primary: "bg-indigo-600 text-white hover:bg-indigo-700",
    ghost: "bg-white text-slate-700 border border-slate-300 hover:bg-slate-50",
    danger: "bg-rose-600 text-white hover:bg-rose-700",
  };
  return (
    <button
      className={`rounded-md px-3 py-2 text-sm font-medium disabled:opacity-50 ${styles[variant]} ${className}`}
      {...props}
    />
  );
}

export function Card({ title, children, actions }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Banner({ kind = "error", children }) {
  if (!children) return null;
  const styles = {
    error: "bg-rose-50 text-rose-800 border-rose-200",
    success: "bg-emerald-50 text-emerald-800 border-emerald-200",
    info: "bg-sky-50 text-sky-800 border-sky-200",
  };
  return (
    <div className={`rounded-md border px-3 py-2 text-sm ${styles[kind]}`} role="status">
      {children}
    </div>
  );
}

export function Field({ label, children }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-slate-700">{label}</span>
      {children}
    </label>
  );
}

export const input =
  "w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none";
