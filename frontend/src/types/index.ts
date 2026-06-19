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
