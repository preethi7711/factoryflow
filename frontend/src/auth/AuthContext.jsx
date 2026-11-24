import { createContext, useContext, useState } from "react";

import { api } from "../api/client.js";

const KEY = "ff.auth";
const AuthContext = createContext(null);

function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(load);

  async function login(username, password) {
    const body = await api("/auth/login", { method: "POST", body: { username, password } });
    const next = { token: body.access_token, role: body.role, username };
    localStorage.setItem(KEY, JSON.stringify(next));
    setAuth(next);
    return next;
  }

  function logout() {
    localStorage.removeItem(KEY);
    setAuth(null);
  }

  return <AuthContext.Provider value={{ auth, login, logout }}>{children}</AuthContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext);
}
