import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type Me, type Panel as PanelData } from "./api";
import { Chat } from "./Chat";
import { Login } from "./Login";
import { Panel } from "./Panel";

export default function App() {
  const [me, setMe] = useState<Me | null | "signed-out">(null);
  const [panel, setPanel] = useState<PanelData | null>(null);

  const loadPanel = useCallback(() => {
    api.panel().then(setPanel).catch(() => setPanel(null));
  }, []);

  useEffect(() => {
    api
      .me()
      .then((who) => {
        setMe(who);
        loadPanel();
      })
      .catch((e) => setMe(e instanceof ApiError && e.status === 401 ? "signed-out" : "signed-out"));
  }, [loadPanel]);

  if (me === null) return <main className="loading muted">Loading…</main>;
  if (me === "signed-out") return <Login />;

  async function signOut() {
    await api.logout();
    setMe("signed-out");
  }

  return (
    <div className="app">
      <header>
        <div>
          <span className="eyebrow">FCI London</span>
          <span className="title">Catalogue assistant</span>
        </div>
        <div className="who">
          <span className="mono">{me.email}</span>
          <button className="ghost" onClick={signOut}>Sign out</button>
        </div>
      </header>
      <div className="layout">
        <Chat
          canRun={me.can_run}
          onRunFinished={loadPanel}
          names={Object.fromEntries((panel?.products ?? []).map((p) => [p.sku, p.name]))}
        />
        <Panel data={panel} />
      </div>
    </div>
  );
}
