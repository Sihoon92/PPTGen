import { expect, test, vi } from "vitest";
import { resumeChat, streamChat } from "./sse";

function streamFromString(s: string): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(s);
  return new ReadableStream({
    start(controller) {
      controller.enqueue(bytes);
      controller.close();
    },
  });
}

test("streamChat reassembles a frame split across two chunks", async () => {
  const full =
    'event: token\ndata: {"delta": "Hello"}\n\n' +
    'event: done\ndata: {"session_id": "s1"}\n\n';
  const mid = 18; // split point inside the first frame
  const enc = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(enc.encode(full.slice(0, mid)));
      controller.enqueue(enc.encode(full.slice(mid)));
      controller.close();
    },
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: stream }));
  const tokens: string[] = [];
  let done = false;
  await streamChat("s1", "hi", "chat", {
    onToken: (d) => tokens.push(d),
    onDone: () => (done = true),
    onError: () => {},
  });
  expect(tokens.join("")).toBe("Hello");
  expect(done).toBe(true);
});

test("streamChat dispatches interrupt events (PPT mode)", async () => {
  const sse =
    'event: interrupt\ndata: {"interrupt": {"question": "누구 대상인가요?", "field": "audience"}}\n\n' +
    'event: done\ndata: {"session_id": "s1"}\n\n';
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: streamFromString(sse) }));
  let question = "";
  await streamChat("s1", "slides", "ppt", {
    onToken: () => {},
    onDone: () => {},
    onError: () => {},
    onInterrupt: (p) => (question = p.question),
  });
  expect(question).toBe("누구 대상인가요?");
});

test("streamChat dispatches node trace events", async () => {
  const sse =
    'event: node\ndata: {"node": "dsl_planner", "label": "슬라이드 DSL 생성", "kind": "llm", "tool": "gemma3n:e4b", "step": 3, "status": "running"}\n\n' +
    'event: node\ndata: {"node": "dsl_planner", "label": "슬라이드 DSL 생성", "kind": "llm", "tool": "gemma3n:e4b", "step": 3, "status": "done", "summary": "슬라이드 2개 생성", "output": {"raw_deck": []}}\n\n' +
    'event: done\ndata: {"session_id": "s1"}\n\n';
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: streamFromString(sse) }));
  const statuses: string[] = [];
  await streamChat("s1", "slides", "ppt", {
    onToken: () => {},
    onDone: () => {},
    onError: () => {},
    onNode: (e) => statuses.push(`${e.node}:${e.status}`),
  });
  expect(statuses).toEqual(["dsl_planner:running", "dsl_planner:done"]);
});

test("resumeChat posts to /resume and dispatches artifact events", async () => {
  const sse =
    'event: artifact\ndata: {"artifact": {"id": "abc", "filename": "deck.pptx", "slide_count": 3, "download_url": "/api/artifacts/abc"}}\n\n' +
    'event: done\ndata: {"session_id": "s1"}\n\n';
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, body: streamFromString(sse) });
  vi.stubGlobal("fetch", fetchMock);
  let artifactId = "";
  await resumeChat("s1", "임원 대상", {
    onToken: () => {},
    onDone: () => {},
    onError: () => {},
    onArtifact: (a) => (artifactId = a.id),
  });
  expect(artifactId).toBe("abc");
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/sessions/s1/resume",
    expect.objectContaining({ method: "POST" }),
  );
});

test("streamChat calls onError for a malformed data frame", async () => {
  const sse = "event: token\ndata: {not-json}\n\n";
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: streamFromString(sse) }));
  const errors: string[] = [];
  await streamChat("s1", "hi", "chat", {
    onToken: () => {},
    onDone: () => {},
    onError: (msg) => errors.push(msg),
  });
  expect(errors.length).toBe(1);
  expect(errors[0]).toMatch(/Malformed SSE frame/);
});

test("streamChat parses token and done events", async () => {
  const sse =
    'event: token\ndata: {"delta": "Hel"}\n\n' +
    'event: token\ndata: {"delta": "lo"}\n\n' +
    'event: done\ndata: {"session_id": "s1"}\n\n';
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, body: streamFromString(sse) }));

  const tokens: string[] = [];
  let done = false;
  await streamChat("s1", "hi", "chat", {
    onToken: (d) => tokens.push(d),
    onDone: () => (done = true),
    onError: () => {},
  });
  expect(tokens.join("")).toBe("Hello");
  expect(done).toBe(true);
});
