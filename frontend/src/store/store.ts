import { create } from "zustand";
import type {
  Artifact,
  ChatMessage,
  Mode,
  OllamaHealth,
  PendingInterrupt,
  Session,
  TraceEntry,
} from "../types";

interface State {
  sessions: Session[];
  activeSessionId: string | null;
  messages: ChatMessage[];
  mode: Mode;
  artifactsOpen: boolean;
  ollama: OllamaHealth | null;
  streaming: boolean;
  pendingInterrupt: PendingInterrupt | null;
  currentArtifact: Artifact | null;
  trace: TraceEntry[];

  setSessions: (s: Session[]) => void;
  setActiveSession: (id: string | null) => void;
  setMessages: (m: ChatMessage[]) => void;
  appendUserMessage: (content: string) => void;
  startAssistantMessage: () => void;
  appendAssistantDelta: (delta: string) => void;
  setLastAssistantContent: (content: string) => void;
  setMode: (mode: Mode) => void;
  toggleArtifacts: () => void;
  setArtifactsOpen: (v: boolean) => void;
  setOllama: (health: OllamaHealth) => void;
  setStreaming: (v: boolean) => void;
  setPendingInterrupt: (i: PendingInterrupt | null) => void;
  setArtifact: (a: Artifact | null) => void;
  addTraceEntry: (e: TraceEntry) => void;
  clearTrace: () => void;
}

export const useStore = create<State>((set) => ({
  sessions: [],
  activeSessionId: null,
  messages: [],
  mode: "chat",
  artifactsOpen: false,
  ollama: null,
  streaming: false,
  pendingInterrupt: null,
  currentArtifact: null,
  trace: [],

  setSessions: (sessions) => set({ sessions }),
  setActiveSession: (activeSessionId) => set({ activeSessionId }),
  setMessages: (messages) => set({ messages }),
  appendUserMessage: (content) =>
    set((s) => ({ messages: [...s.messages, { role: "user", content }] })),
  startAssistantMessage: () =>
    set((s) => ({ messages: [...s.messages, { role: "assistant", content: "" }] })),
  appendAssistantDelta: (delta) =>
    set((s) => {
      const messages = s.messages.slice();
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = { ...last, content: last.content + delta };
      }
      return { messages };
    }),
  setLastAssistantContent: (content) =>
    set((s) => {
      const messages = s.messages.slice();
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        messages[messages.length - 1] = { ...last, content };
      }
      return { messages };
    }),
  setMode: (mode) => set({ mode }),
  toggleArtifacts: () => set((s) => ({ artifactsOpen: !s.artifactsOpen })),
  setArtifactsOpen: (artifactsOpen) => set({ artifactsOpen }),
  setOllama: (ollama) => set({ ollama }),
  setStreaming: (streaming) => set({ streaming }),
  setPendingInterrupt: (pendingInterrupt) => set({ pendingInterrupt }),
  setArtifact: (currentArtifact) => set({ currentArtifact }),
  // Upsert by (node, step): a node's "running" entry is replaced by its "done"/"error".
  addTraceEntry: (e) =>
    set((s) => {
      const i = s.trace.findIndex((t) => t.node === e.node && t.step === e.step);
      if (i === -1) return { trace: [...s.trace, e] };
      const trace = s.trace.slice();
      trace[i] = e;
      return { trace };
    }),
  clearTrace: () => set({ trace: [] }),
}));
