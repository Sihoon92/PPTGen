import { useState } from "react";
import { createSession, listSessions } from "../../api/client";
import { streamChat } from "../../api/sse";
import { useStore } from "../../store/store";

export default function Composer() {
  const [text, setText] = useState("");
  const mode = useStore((s) => s.mode);
  const streaming = useStore((s) => s.streaming);
  const activeSessionId = useStore((s) => s.activeSessionId);
  const appendUserMessage = useStore((s) => s.appendUserMessage);
  const startAssistantMessage = useStore((s) => s.startAssistantMessage);
  const setLastAssistantContent = useStore((s) => s.setLastAssistantContent);
  const setStreaming = useStore((s) => s.setStreaming);
  const setSessions = useStore((s) => s.setSessions);
  const setActiveSession = useStore((s) => s.setActiveSession);
  const setMessages = useStore((s) => s.setMessages);

  const onSend = async () => {
    const content = text.trim();
    if (!content || streaming) return;

    // 활성 세션이 없으면 자동으로 새 세션을 만든다 (바로 입력 → 전송이 동작하도록).
    let sessionId = activeSessionId;
    if (!sessionId) {
      const session = await createSession();
      sessionId = session.id;
      setActiveSession(session.id);
      setMessages([]);
    }

    setText("");
    appendUserMessage(content);
    startAssistantMessage();
    setStreaming(true);

    // 스트리밍 중에는 화면에 부분 출력하지 않고 버퍼에 모았다가, 완료 시 한 번에 커밋한다.
    // 그래야 응답 전체를 마크다운/다이어그램으로 깔끔하게 렌더할 수 있다.
    let buffer = "";
    await streamChat(sessionId, content, mode, {
      onToken: (d) => {
        buffer += d;
      },
      onDone: () => {
        setLastAssistantContent(buffer);
        setStreaming(false);
        // Refresh the session list so the auto-titled session appears in the sidebar.
        listSessions().then(setSessions).catch(() => {});
      },
      onError: (msg) => {
        setLastAssistantContent(buffer ? `${buffer}\n\n[오류] ${msg}` : `[오류] ${msg}`);
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
