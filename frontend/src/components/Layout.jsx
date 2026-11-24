import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext.jsx";
import { Logo } from "./SnackArt.jsx";

// Which nav links each role sees (spec section 2).
const NAV = {
  salesman: [["/order", "New order"]],
  admin: [
    ["/orders", "Orders"],
    ["/stock", "Stock & reports"],
  ],
  production: [["/production", "Production"]],
  auditor: [["/stock", "Stock & reports"]],
  owner: [["/stock", "Stock & reports"]],
};

const ROLE_NAME = {
  salesman: "Salesman",
  admin: "Billing desk",
  production: "Production floor",
  auditor: "Auditor (read-only)",
  owner: "Owner",
};

// The salesman works one-handed on a phone: a narrow column on warm cream. Desk roles get a wider page.
const WIDTH = { salesman: "max-w-lg" };

export default function Layout() {
  const { auth, logout } = useAuth();
  const navigate = useNavigate();
  const role = auth?.role;
  const links = (role && NAV[role]) || [];
  const width = WIDTH[role] || "max-w-5xl";

  return (
    <div className={`min-h-screen ${role === "salesman" ? "bg-cream" : "bg-paper"}`}>
      <header className="sticky top-0 z-20 border-b border-line bg-paper/95 backdrop-blur">
        <div className={`mx-auto flex ${width} items-center justify-between gap-3 px-4 py-2`}>
          <div className="flex min-w-0 items-center gap-4">
            <span className="flex items-center gap-2">
              <Logo className="h-8 w-8" />
              <span className="font-display text-lg font-extrabold tracking-tight">
                FactoryFlow
              </span>
            </span>
            <nav className="flex gap-1 text-sm" aria-label="Main">
              {links.map(([to, label]) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    `rounded-full px-3 py-1.5 font-medium ${
                      isActive
                        ? "bg-turmeric-100 text-choc-900"
                        : "text-choc-500 hover:text-choc-900"
                    }`
                  }
                >
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>
          {auth && (
            <div className="flex shrink-0 items-center gap-3 text-sm">
              <span className="hidden text-right leading-tight text-choc-500 sm:block">
                <span className="block font-medium text-choc-900">{auth.username}</span>
                {ROLE_NAME[role] || role}
              </span>
              <button
                className="rounded-full px-3 py-1.5 text-choc-500 underline-offset-2 hover:text-choc-900 hover:underline"
                onClick={() => {
                  logout();
                  navigate("/login");
                }}
              >
                Log out
              </button>
            </div>
          )}
        </div>
      </header>
      <main className={`mx-auto ${width} space-y-4 px-4 py-5`}>
        <Outlet />
      </main>
    </div>
  );
}
