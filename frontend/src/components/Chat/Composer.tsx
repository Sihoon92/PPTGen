import { useState } from "react";
import { listSessions } from "../../api/client";
import { streamChat } from "../../api/sse";
import { useStore } from "../../store/store";

export default function Composer() {
  const [text, setText] = useState("");
  const mode = useStore((s) => s.mode);
  const streaming = useStore((s) => s.streaming);
  const activeSessionId = useStore((s) => s.activeSessionId);
  const appendUserMessage = useStore((s) => s.appendUserMessage);
  const startAssistantMessage = useStore((s) => s.startAssistantMessage);
  const appendAssistantDelta = useStore((s) => s.appendAssistantDelta);
  const setStreaming = useStore((s) => s.setStreaming);
  const setSessions = useStore((s) => s.setSessions);

  const onSend = async () => {
    const content = text.trim();
    if (!content || streaming || !activeSessionId) return;
    setText("");
    appendUserMessage(content);
    startAssistantMessage();
    setStreaming(true);
    await streamChat(activeSessionId, content, mode, {
      onToken: (d) => appendAssistantDelta(d),
      onDone: () => {
        setStreaming(false);
        // Refresh the session list so the auto-titled session appears in the sidebar.
        listSessions().then(setSessions).catch(() => {});
      },
      onError: (msg) => {
        appendAssistantDelta(`\n[오류] ${msg}`);
        setStreaming(false);
      },
    });
  };

  return (
    <div className="flex gap-2 border-t border-paper-dark p-3">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend();
          }
        }}
        rows={2}
        placeholder="메시지를 입력하세요…"
        className="flex-1 resize-none rounded-md border border-paper-dark bg-white p-2 text-sm outline-none"
      />
      <button
        onClick={onSend}
        disabled={streaming}
        className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
      >
        전송
      </button>
    </div>
  );
}
