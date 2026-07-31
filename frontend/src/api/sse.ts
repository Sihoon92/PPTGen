import type { Artifact, Mode, PendingInterrupt, TraceEntry } from "../types";
import { API_HEADERS } from "./headers";

export interface StreamHandlers {
  onToken: (delta: string) => void;
  onDone: () => void;
  onError: (message: string) => void;
  // PPT mode only:
  onInterrupt?: (payload: PendingInterrupt) => void;
  onArtifact?: (payload: Artifact) => void;
  onNode?: (entry: TraceEntry) => void;
}

async function readSSE(res: Response, handlers: StreamHandlers): Promise<void> {
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
        else if (event === "interrupt") handlers.onInterrupt?.(data.interrupt);
        else if (event === "artifact") handlers.onArtifact?.(data.artifact);
        else if (event === "node") handlers.onNode?.(data);
      } catch {
        handlers.onError(`Malformed SSE frame: ${raw}`);
      }
    }
  }
}

export async function streamChat(
  sessionId: string,
  content: string,
  mode: Mode,
  handlers: StreamHandlers,
): Promise<void> {
  const res = await fetch(`/api/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { ...API_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify({ content, mode }),
  });
  await readSSE(res, handlers);
}

// Resume a PPT pipeline paused on a clarifying-question interrupt.
export async function resumeChat(
  sessionId: string,
  answer: string,
  handlers: StreamHandlers,
): Promise<void> {
  const res = await fetch(`/api/sessions/${sessionId}/resume`, {
    method: "POST",
    headers: { ...API_HEADERS, "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  });
  await readSSE(res, handlers);
}
