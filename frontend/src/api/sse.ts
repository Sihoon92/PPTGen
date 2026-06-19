import type { Mode } from "../types";

export interface StreamHandlers {
  onToken: (delta: string) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

export async function streamChat(
  sessionId: string,
  content: string,
  mode: Mode,
  handlers: StreamHandlers,
): Promise<void> {
  const res = await fetch(`/api/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, mode }),
  });
  if (!res.ok || !res.body) {
    handlers.onError(`HTTP ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const event = /event: (.*)/.exec(raw)?.[1]?.trim();
      const dataLine = /data: (.*)/.exec(raw)?.[1] ?? "{}";
      try {
        const data = JSON.parse(dataLine);
        if (event === "token") handlers.onToken(data.delta ?? "");
        else if (event === "done") handlers.onDone();
        else if (event === "error") handlers.onError(data.message ?? "unknown error");
      } catch {
        handlers.onError(`Malformed SSE frame: ${raw}`);
      }
    }
  }
}
