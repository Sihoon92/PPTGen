import { afterEach, expect, test, vi } from "vitest";
import { createSession, listSessions, checkOllama } from "./client";

afterEach(() => vi.restoreAllMocks());

test("listSessions GETs /api/sessions", async () => {
  const data = [{ id: "1", title: "A", mode: "chat", created_at: "", updated_at: "" }];
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => data }));
  expect(await listSessions()).toEqual(data);
  expect(fetch).toHaveBeenCalledWith("/api/sessions", expect.objectContaining({ method: "GET" }));
});

test("createSession POSTs title", async () => {
  const session = { id: "2", title: "X", mode: "chat", created_at: "", updated_at: "" };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => session }));
  expect(await createSession("X")).toEqual(session);
  const [, opts] = (fetch as any).mock.calls[0];
  expect(opts.method).toBe("POST");
  expect(JSON.parse(opts.body)).toEqual({ title: "X" });
});

test("checkOllama returns health", async () => {
  const health = { ok: true, models: ["gemma3n:e4b"], error: null };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => health }));
  expect(await checkOllama()).toEqual(health);
});
