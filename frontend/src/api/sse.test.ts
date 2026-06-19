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
