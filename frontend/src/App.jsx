import { useEffect, useState } from "react";

// P1b placeholder: proves the built frontend and the API are served from the same URL.
// The real screens arrive in P8.
export default function App() {
  const [health, setHealth] = useState("checking...");

  useEffect(() => {
    fetch("/api/v1/health")
      .then((r) => r.json())
      .then((body) => setHealth(`API ${body.status}, database ${body.db}`))
      .catch(() => setHealth("API unreachable"));
  }, []);

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem", maxWidth: 480 }}>
      <h1>FactoryFlow</h1>
      <p>Order-to-audit system. The app screens are coming soon.</p>
      <p>
        Status: <strong>{health}</strong>
      </p>
    </main>
  );
}
