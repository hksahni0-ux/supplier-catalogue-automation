// Typed calls to the Python API. Every write sends X-Requested-With, which the server requires.

export type Me = { email: string; can_run: boolean };
export type Proposal = { action: "run"; skus: string[]; publish: boolean };
export type ChatMessage = { role: "user" | "assistant"; content: string };
export type ChatReply = { text: string; verified: boolean; proposals: Proposal[]; tools_used: string[] };
export type Product = {
  sku: string;
  name: string;
  currency: string;
  base_price: number | null;
  price_range: [number, number] | null;
  price_rows: number | null;
  needs_review: number;
  last_run: string | null;
  drive?: string | null;
};
export type ReviewItem = { product: string; severity: string; about: string; message: string };
export type Panel = { products: Product[]; review: { items: ReviewItem[] } };
export type RunResult = {
  sku: string;
  name: string;
  base_price: number;
  combinations: number;
  changes: string | null;
  drive: string | null;
  error: string | null;
};
export type RunStatus = {
  id: string;
  state: "queued" | "running" | "done" | "failed";
  log: string[];
  results: RunResult[];
  error: string | null;
};

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...init,
    headers: { "Content-Type": "application/json", "X-Requested-With": "fci", ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new ApiError(response.status, typeof detail === "string" ? detail : "request failed");
  }
  return (await response.json()) as T;
}

const post = <T,>(path: string, body: unknown) => call<T>(path, { method: "POST", body: JSON.stringify(body) });

export const api = {
  me: () => call<Me>("/api/me"),
  login: (email: string) => post<{ status: string }>("/api/login", { email }),
  logout: () => post<{ status: string }>("/api/logout", {}),
  chat: (messages: ChatMessage[]) => post<ChatReply>("/api/chat", { messages }),
  panel: () => call<Panel>("/api/products"),
  startRun: (proposal: Proposal) => post<{ id: string }>("/api/runs", { skus: proposal.skus, publish: proposal.publish }),
  run: (id: string) => call<RunStatus>(`/api/runs/${encodeURIComponent(id)}`),
};
