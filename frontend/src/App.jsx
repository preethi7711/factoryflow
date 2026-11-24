import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthContext.jsx";
import Layout from "./components/Layout.jsx";
import { HOME } from "./nav.js";
import AdminOrdersPage from "./pages/AdminOrdersPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import OrderPage from "./pages/OrderPage.jsx";
import ProductionPage from "./pages/ProductionPage.jsx";
import StockPage from "./pages/StockPage.jsx";

function Protected({ roles, children }) {
  const { auth } = useAuth();
  if (!auth) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(auth.role)) {
    return <Navigate to={HOME[auth.role] || "/login"} replace />;
  }
  return children;
}

export default function App() {
  const { auth } = useAuth();
  const home = (auth && HOME[auth.role]) || "/login";
  return (
    <Routes>
      <Route path="/login" element={auth ? <Navigate to={home} replace /> : <LoginPage />} />
      <Route element={<Layout />}>
        <Route
          path="/order"
          element={
            <Protected roles={["salesman"]}>
              <OrderPage />
            </Protected>
          }
        />
        <Route
          path="/orders"
          element={
            <Protected roles={["admin"]}>
              <AdminOrdersPage />
            </Protected>
          }
        />
        <Route
          path="/production"
          element={
            <Protected roles={["production"]}>
              <ProductionPage />
            </Protected>
          }
        />
        <Route
          path="/stock"
          element={
            <Protected roles={["admin", "auditor", "owner"]}>
              <StockPage />
            </Protected>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to={home} replace />} />
    </Routes>
  );
}
