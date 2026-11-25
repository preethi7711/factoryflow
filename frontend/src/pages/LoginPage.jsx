import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext.jsx";
import { HOME } from "../nav.js";
import { Logo } from "../components/SnackArt.jsx";
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
    <div className="min-h-screen bg-cream">
      <div className="kolam h-2 bg-turmeric-500" aria-hidden="true" />
      <div className="mx-auto max-w-sm px-4 pt-14">
        <div className="mb-6 flex items-center gap-3">
          <Logo className="h-12 w-12" />
          <div>
            <h1 className="text-3xl font-extrabold">FactoryFlow</h1>
            <p className="text-sm text-choc-500">
              From the salesman&apos;s order to the auditor&apos;s report.
            </p>
          </div>
        </div>
        <form onSubmit={submit} className="space-y-4 rounded-2xl border border-line bg-paper p-5">
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
    </div>
  );
}
