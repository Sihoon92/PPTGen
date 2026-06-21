import type { StreamHandlers } from "./sse";
import { resumeChat, streamChat } from "./sse";
import { listSessions } from "./client";
import { useStore } from "../store/store";
import type { Mode } from "../types";

// Builds handlers that drive the store directly, so both a fresh send and an
// interrupt resume share one streaming code path (and chained interrupts work).
function makeHandlers(): StreamHandlers {
  let buffer = "";
  return {
    onToken: (d) => {
      buffer += d;
    },
    onInterrupt: (payload) => {
      const st = useStore.getState();
      st.setPendingInterrupt(payload);
      // surface the question as the assistant's message in the thread
      st.setLastAssistantContent(payload.question);
    },
    onArtifact: (payload) => {
      const st = useStore.getState();
      st.setArtifact(payload);
      st.setArtifactsOpen(true);
    },
    onNode: (entry) => {
      const st = useStore.getState();
      st.addTraceEntry(entry);
      // surface the debug view as soon as the PPT pipeline starts running
      st.setArtifactsOpen(true);
    },
    onDone: () => {
      const st = useStore.getState();
      // a pending interrupt already set the assistant content to the question
      if (!st.pendingInterrupt && buffer) st.setLastAssistantContent(buffer);
      st.setStreaming(false);
      listSessions().then(st.setSessions).catch(() => {});
    },
    onError: (msg) => {
      const st = useStore.getState();
      st.setLastAssistantContent(buffer ? `${buffer}\n\n[오류] ${msg}` : `[오류] ${msg}`);
      st.setStreaming(false);
    },
  };
}

function beginTurn(content: string) {
  const st = useStore.getState();
  st.appendUserMessage(content);
  st.startAssistantMessage();
  st.setPendingInterrupt(null);
  st.clearTrace();
  st.setStreaming(true);
}

export async function sendMessage(sessionId: string, content: string, mode: Mode): Promise<void> {
  beginTurn(content);
  await streamChat(sessionId, content, mode, makeHandlers());
}

export async function resumeMessage(sessionId: string, answer: string): Promise<void> {
  beginTurn(answer);
  await resumeChat(sessionId, answer, makeHandlers());
}
