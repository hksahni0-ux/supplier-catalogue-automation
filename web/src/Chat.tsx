import { useRef, useState, type FormEvent } from "react";
import { api, type ChatMessage, type Proposal } from "./api";
import { RichText } from "./RichText";
import { RunCard } from "./RunCard";

type Turn = ChatMessage & { verified?: boolean; proposals?: Proposal[]; tools?: string[] };

const SUGGESTIONS = [
  "What does Richard size D cost in glove leather?",
  "Which products need a person to check something?",
  "What sizes and fabrics does Burt come in?",
  "What changed since the last run?",
];

type Props = { canRun: boolean; onRunFinished: () => void; names: Record<string, string> };

export function Chat({ canRun, onRunFinished, names }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  async function ask(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    const history: Turn[] = [...turns, { role: "user", content: text }];
    setTurns(history);
    setDraft("");
    setBusy(true);
    setError(null);
    try {
      // the server only needs the words; flags and proposals stay in the page
      const reply = await api.chat(history.slice(-20).map(({ role, content }) => ({ role, content })));
      setTurns([...history, { role: "assistant", content: reply.text, verified: reply.verified,
        proposals: reply.proposals, tools: reply.tools_used }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setTimeout(() => end.current?.scrollIntoView?.({ behavior: "smooth" }), 0);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    ask(draft);
  }

  return (
    <section className="chat" aria-label="Assistant">
      <div className="messages">
        {turns.length === 0 && (
          <div className="welcome">
            <h2>Ask about the catalogue</h2>
            <p className="muted">Answers come only from the latest run outputs. Prices are the suppliers' list prices.</p>
            <div className="suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} className="ghost" onClick={() => ask(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn, i) => (
          <div key={i} className={`bubble ${turn.role}`}>
            {turn.role === "assistant" ? <RichText text={turn.content} /> : <p>{turn.content}</p>}
            {turn.role === "assistant" && (
              <p className={`check ${turn.verified ? "ok" : "warn"}`}>
                {turn.verified ? "✓ Checked against the data" : "⚠ Not verified — no figures shown"}
                {turn.tools && turn.tools.length > 0 && <span className="muted"> · {turn.tools.join(", ")}</span>}
              </p>
            )}
            {turn.proposals?.map((p, j) => <RunCard key={j} proposal={p} canRun={canRun} onDone={onRunFinished} names={names} />)}
          </div>
        ))}
        {busy && <div className="bubble assistant typing" aria-live="polite">Looking that up…</div>}
        {error && <p className="error" role="alert">{error}</p>}
        <div ref={end} />
      </div>
      <form className="composer" onSubmit={submit}>
        <input aria-label="Ask the assistant" value={draft} onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about a price, option, change or run…" maxLength={2000} />
        <button type="submit" disabled={busy || !draft.trim()}>Ask</button>
      </form>
    </section>
  );
}
