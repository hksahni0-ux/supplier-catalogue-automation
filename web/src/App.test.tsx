import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";

type Route = (body: unknown) => { status?: number; json: unknown };
let routes: Record<string, Route>;
let calls: { method: string; path: string; body: unknown; headers: Record<string, string> }[];

const PANEL = {
  products: [
    {
      sku: "cattelan-italia-806", name: "Thomas Double Bed", currency: "EUR", base_price: 4002,
      price_range: [4002, 6857], price_rows: 560, needs_review: 0, last_run: null, drive: null,
    },
    {
      sku: "cattelan-italia-889", name: "Richard Double Bed", currency: "EUR", base_price: 4121,
      price_range: [4121, 8769], price_rows: 2340, needs_review: 2, last_run: "2026-11-01 22:58 UTC",
      drive: "https://drive.google.com/drive/folders/abc",
    },
    {
      sku: "fiera-collection-043", name: "Burt Corner Sofa", currency: "GBP", base_price: 1650,
      price_range: [1650, 4073], price_rows: 768, needs_review: 4, last_run: null, drive: null,
    },
  ],
  review: { items: [{ product: "Burt Corner Sofa", severity: "warning", about: "catcode", message: "confirm FUR-SEA-SOF" }] },
};

beforeEach(() => {
  calls = [];
  routes = {
    "GET /api/me": () => ({ json: { email: "ria@fcilondon.co.uk", can_run: true } }),
    "GET /api/products": () => ({ json: PANEL }),
  };
  vi.stubGlobal("fetch", async (path: string, init: RequestInit = {}) => {
    const method = init.method ?? "GET";
    const body = init.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path, body, headers: (init.headers ?? {}) as Record<string, string> });
    const route = routes[`${method} ${path}`];
    const reply = route ? route(body) : { status: 404, json: { detail: "not found" } };
    const status = reply.status ?? 200;
    return { ok: status < 400, status, statusText: "", json: async () => reply.json } as Response;
  });
});
afterEach(() => vi.unstubAllGlobals());

test("signed-out visitors get the email sign-in form", async () => {
  routes["GET /api/me"] = () => ({ status: 401, json: { detail: "sign in first" } });
  routes["POST /api/login"] = () => ({ json: { status: "sent" } });
  render(<App />);
  await userEvent.type(await screen.findByLabelText(/work email/i), "ria@fcilondon.co.uk");
  await userEvent.click(screen.getByRole("button", { name: /email me a sign-in link/i }));
  expect(await screen.findByText(/check your inbox/i)).toBeInTheDocument();
  const login = calls.find((c) => c.path === "/api/login")!;
  expect(login.body).toEqual({ email: "ria@fcilondon.co.uk" });
  expect(login.headers["X-Requested-With"]).toBe("fci");
});

test("the side panel shows each product with its own currency and review count", async () => {
  render(<App />);
  expect(await screen.findByText("Richard Double Bed")).toBeInTheDocument();
  expect(screen.getByText("€4,121")).toBeInTheDocument();
  expect(screen.getByText("£1,650")).toBeInTheDocument();
  expect(screen.getByText("2,340 price rows")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /richard double bed in drive/i })).toHaveAttribute(
    "href", "https://drive.google.com/drive/folders/abc",
  );
  expect(screen.getByText(/confirm FUR-SEA-SOF/)).toBeInTheDocument();
});

test("a question gets the assistant's answer, marked as checked", async () => {
  routes["POST /api/chat"] = () => ({
    json: { text: "Richard size D in glove leather: **€7,192**.", verified: true, proposals: [], tools_used: ["get_price"] },
  });
  render(<App />);
  await userEvent.type(await screen.findByRole("textbox", { name: /ask/i }), "Richard D glove?{Enter}");
  expect(await screen.findByText("€7,192")).toContainHTML("strong");
  expect(screen.getByText(/checked against the data/i)).toBeInTheDocument();
  const chat = calls.find((c) => c.path === "/api/chat")!;
  expect(chat.body).toEqual({ messages: [{ role: "user", content: "Richard D glove?" }] });
});

test("an unverified answer is shown as a warning", async () => {
  routes["POST /api/chat"] = () => ({
    json: { text: "I couldn't verify that answer.", verified: false, proposals: [], tools_used: [] },
  });
  render(<App />);
  await userEvent.type(await screen.findByRole("textbox", { name: /ask/i }), "price?{Enter}");
  expect(await screen.findByText(/not verified/i)).toBeInTheDocument();
});

test("a proposed run waits for Confirm, then shows the result with its Drive link", async () => {
  routes["POST /api/chat"] = () => ({
    json: {
      text: "Press Confirm to re-run Thomas.", verified: true,
      proposals: [{ action: "run", skus: ["cattelan-italia-806"], publish: true }], tools_used: ["propose_run"],
    },
  });
  routes["POST /api/runs"] = () => ({ json: { id: "job1" } });
  routes["GET /api/runs/job1"] = () => ({
    json: {
      id: "job1", state: "done", log: ["Finished."], error: null,
      results: [{ sku: "cattelan-italia-806", name: "Thomas Double Bed", base_price: 4002, combinations: 560,
        changes: "no price changes (560 unchanged)", drive: "https://drive.google.com/drive/folders/t1", error: null }],
    },
  });
  render(<App />);
  await userEvent.type(await screen.findByRole("textbox", { name: /ask/i }), "re-run Thomas{Enter}");
  const confirm = await screen.findByRole("button", { name: /confirm/i });
  expect(document.querySelector(".run-head")).toHaveTextContent("Re-run Thomas Double Bed from the latest Drive price lists");
  expect(calls.some((c) => c.path === "/api/runs")).toBe(false); // nothing runs before Confirm
  await userEvent.click(confirm);
  expect(await screen.findByText(/no price changes \(560 unchanged\)/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /thomas double bed results in drive/i })).toHaveAttribute(
    "href", "https://drive.google.com/drive/folders/t1",
  );
  expect(calls.find((c) => c.path === "/api/runs")!.body).toEqual({ skus: ["cattelan-italia-806"], publish: true });
});

test("viewers who can't run see why instead of a Confirm button", async () => {
  routes["GET /api/me"] = () => ({ json: { email: "viewer@x.com", can_run: false } });
  routes["POST /api/chat"] = () => ({
    json: { text: "Press Confirm.", verified: true, proposals: [{ action: "run", skus: ["a"], publish: true }], tools_used: [] },
  });
  render(<App />);
  await userEvent.type(await screen.findByRole("textbox", { name: /ask/i }), "run a{Enter}");
  expect(await screen.findByText(/your account can view but not run/i)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /confirm/i })).not.toBeInTheDocument();
});

test("assistant text is never treated as HTML", async () => {
  routes["POST /api/chat"] = () => ({
    json: { text: "<img src=x onerror=alert(1)>", verified: true, proposals: [], tools_used: [] },
  });
  const { container } = render(<App />);
  await userEvent.type(await screen.findByRole("textbox", { name: /ask/i }), "x{Enter}");
  expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
  expect(container.querySelector("img")).toBeNull();
});
