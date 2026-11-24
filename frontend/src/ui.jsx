// Shared building blocks so pages stay short. Colours and fonts come from tailwind.config.js tokens.

const BUTTON = {
  primary: "bg-choc-900 text-cream hover:bg-choc-700",
  accent: "bg-turmeric-500 text-choc-900 hover:bg-turmeric-300",
  ghost: "bg-paper text-choc-900 border border-line hover:bg-cream",
  danger: "bg-chilli-500 text-paper hover:bg-chilli-700",
};

export function Button({ className = "", variant = "primary", ...props }) {
  return (
    <button
      className={`min-h-[44px] rounded-full px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${BUTTON[variant]} ${className}`}
      {...props}
    />
  );
}

export function Card({ title, children, actions, className = "" }) {
  return (
    <section className={`rounded-2xl border border-line bg-paper p-4 sm:p-5 ${className}`}>
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-3">
          {title && <h2 className="text-lg font-semibold">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

const BANNER = {
  error: "bg-chilli-50 text-chilli-700 border-chilli-100",
  success: "bg-leaf-50 text-leaf-700 border-leaf-100",
  info: "bg-turmeric-50 text-choc-700 border-turmeric-100",
};

export function Banner({ kind = "error", children }) {
  if (!children) return null;
  return (
    <div
      className={`animate-fade-in rounded-xl border px-3 py-2 text-sm ${BANNER[kind]}`}
      role="status"
    >
      {children}
    </div>
  );
}

export function Field({ label, children }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-choc-700">{label}</span>
      {children}
    </label>
  );
}

// A status word in a coloured pill. `tone` picks the colour; the text always says the status.
const PILL = {
  wait: "bg-turmeric-100 text-choc-900",
  ok: "bg-leaf-100 text-leaf-700",
  bad: "bg-chilli-100 text-chilli-700",
  muted: "bg-choc-100 text-choc-700",
};

export function Pill({ tone = "muted", children }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${PILL[tone]}`}>
      {children}
    </span>
  );
}

export const input =
  "min-h-[44px] w-full rounded-xl border border-line bg-paper px-3 py-2 text-sm text-choc-900 placeholder:text-choc-300 focus:border-turmeric-700 focus:outline-none";
