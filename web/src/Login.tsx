import { useState, type FormEvent } from "react";
import { api, ApiError } from "./api";

export function Login() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setState("sending");
    setError(null);
    try {
      await api.login(email);
      setState("sent");
    } catch (e) {
      setState("idle");
      setError(e instanceof ApiError && e.status === 422 ? "That doesn't look like an email address." : (e as Error).message);
    }
  }

  return (
    <main className="login">
      <div className="login-card">
        <p className="eyebrow">FCI London</p>
        <h1>Catalogue assistant</h1>
        <p className="muted">Supplier price lists in, upload sheets out. Ask about any product, review what needs a
          person, and re-run products from the latest price lists.</p>
        {state === "sent" ? (
          <p className="notice" role="status">Check your inbox: a sign-in link is on its way to <b>{email}</b>.
            It works once and expires in 15 minutes.</p>
        ) : (
          <form onSubmit={submit}>
            <label htmlFor="email">Work email</label>
            <input id="email" type="email" required autoComplete="email" value={email}
              onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" />
            <button type="submit" disabled={state === "sending"}>
              {state === "sending" ? "Sending…" : "Email me a sign-in link"}
            </button>
            {error && <p className="error" role="alert">{error}</p>}
          </form>
        )}
      </div>
    </main>
  );
}
