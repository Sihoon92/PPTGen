export type Mode = "chat" | "ppt";

export interface Session {
  id: string;
  title: string;
  mode: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface OllamaHealth {
  ok: boolean;
  models: string[];
  error: string | null;
}

// A clarifying question raised by the PPT pipeline (LangGraph interrupt).
export interface PendingInterrupt {
  field?: string;
  question: string;
  choices?: string[];
}

// A generated, downloadable deck.
export interface Artifact {
  id: string;
  filename: string;
  slide_count: number;
  download_url: string;
}

// One node-execution record from the PPT subgraph (debug/trace view).
export interface TraceEntry {
  run_id: string;
  node: string;
  label: string;
  kind: string;
  tool: string | null;
  step: number;
  ts: string;
  status: "running" | "done" | "error";
  summary?: string;
  output?: unknown;
  error?: string;
}
