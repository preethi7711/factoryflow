import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext.jsx";
import { HOME } from "../nav.js";
import { Banner, Button, Field, input } from "../ui.jsx";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const next = await login(username.trim(), password);
      navigate(HOME[next.role] || "/", { replace: true });
    } catch (err) {
      setError(err.code === "INVALID_CREDENTIALS" ? "Wrong username or password." : err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto mt-16 max-w-sm px-4">
      <h1 className="mb-1 text-2xl font-semibold text-indigo-700">FactoryFlow</h1>
      <p className="mb-6 text-sm text-slate-500">Order-to-audit system. Sign in to continue.</p>
      <form
        onSubmit={submit}
        className="space-y-4 rounded-lg border border-slate-200 bg-white p-5 shadow-sm"
      >
        <Field label="Username">
          <input
            className={input}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
          />
        </Field>
        <Field label="Password">
          <input
            className={input}
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </Field>
        <Banner>{error}</Banner>
        <Button type="submit" disabled={busy || !username || !password} className="w-full">
          {busy ? "Signing in…" : "Sign in"}
        </Button>
      </form>
    </div>
  );
}
