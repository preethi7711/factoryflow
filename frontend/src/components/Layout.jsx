import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext.jsx";

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

export default function Layout() {
  const { auth, logout } = useAuth();
  const navigate = useNavigate();
  const links = (auth && NAV[auth.role]) || [];

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-4">
            <span className="font-semibold text-indigo-700">FactoryFlow</span>
            <nav className="flex gap-3 text-sm">
              {links.map(([to, label]) => (
                <NavLink
                  key={to}
                  to={to}
                  className={({ isActive }) =>
                    isActive ? "font-medium text-indigo-700" : "text-slate-600 hover:text-slate-900"
                  }
                >
                  {label}
                </NavLink>
              ))}
            </nav>
          </div>
          {auth && (
            <div className="flex items-center gap-3 text-sm">
              <span className="text-slate-500">
                {auth.username} · {auth.role}
              </span>
              <button
                className="text-slate-600 underline hover:text-slate-900"
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
      <main className="mx-auto max-w-3xl space-y-4 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
