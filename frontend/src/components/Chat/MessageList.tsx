import type { ChatMessage } from "../../types";

export default function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
      {messages.map((m, i) => (
        <div
          key={i}
          className={`max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm ${
            m.role === "user"
              ? "self-end bg-accent text-white"
              : "self-start bg-white text-ink"
          }`}
        >
          {m.content}
        </div>
      ))}
    </div>
  );
}
