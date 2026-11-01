import { useEffect, useState } from "react";
import { api, type Proposal, type RunStatus } from "./api";

const POLL_MS = 2000;

type Props = { proposal: Proposal; canRun: boolean; onDone: () => void; names: Record<string, string> };

export function RunCard({ proposal, canRun, onDone, names }: Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const next = await api.run(jobId);
        if (stopped) return;
        setStatus(next);
        if (next.state === "done" || next.state === "failed") onDone();
        else timer = setTimeout(poll, POLL_MS);
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      }
    };
    poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [jobId, onDone]);

  async function confirm() {
    setError(null);
    try {
      setJobId((await api.startRun(proposal)).id);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (dismissed) return <div className="run-card muted">Cancelled. Nothing was run.</div>;
  const label = (sku: string) => names[sku] ?? sku;
  const what = proposal.skus.length <= 3 ? proposal.skus.map(label).join(", ") : `${proposal.skus.length} products`;
  return (
    <div className="run-card">
      <div className="run-head">
        <span className="eyebrow">Proposed run</span>
        <span>
          Re-run <b>{what}</b> from the latest Drive price lists{proposal.publish ? " and save results to Drive" : ""}.
        </span>
      </div>
      {!jobId &&
        (canRun ? (
          <div className="run-actions">
            <button onClick={confirm}>Confirm</button>
            <button className="ghost" onClick={() => setDismissed(true)}>Cancel</button>
          </div>
        ) : (
          <p className="muted">Your account can view but not run products. Ask an operator to confirm.</p>
        ))}
      {status && (
        <div className="run-status">
          <span className={`pill ${status.state}`}>{status.state}</span>
          {status.state !== "done" && status.log.slice(-1).map((line) => <span key={line} className="muted">{line}</span>)}
          {status.error && <p className="error">{status.error}</p>}
          {status.results.map((r) => (
            <div key={r.sku} className="run-result">
              <b>{r.name || r.sku}</b>
              {r.error ? (
                <span className="error">{r.error}</span>
              ) : (
                <>
                  <span>{r.combinations.toLocaleString("en-GB")} price rows · {r.changes ?? "first run"}</span>
                  {r.drive && (
                    <a href={r.drive} target="_blank" rel="noreferrer" aria-label={`${r.name} results in Drive`}>
                      Open in Drive
                    </a>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
