import { expect, test, vi } from "vitest";
import { streamChat } from "./sse";

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
