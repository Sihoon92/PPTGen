import { useState } from "react";
import { resumeMessage } from "../../api/chatRunner";
import { useStore } from "../../store/store";

// Rendered when the PPT pipeline pauses to ask the user a clarifying question.
// Submitting the answer resumes the graph via /resume.
export default function InterruptPrompt() {
  const pending = useStore((s) => s.pendingInterrupt);
  const streaming = useStore((s) => s.streaming);
  const activeSessionId = useStore((s) => s.activeSessionId);
  const [answer, setAnswer] = useState("");

  if (!pending) return null;

  const submit = async (value: string) => {
    const text = value.trim();
    if (!text || streaming || !activeSessionId) return;
    setAnswer("");
    await resumeMessage(activeSessionId, text);
  };

  return (
    <div
      data-testid="interrupt-prompt"
      className="mx-3 mb-2 rounded-md border border-accent/40 bg-accent/5 p-3"
    >
      <p className="text-sm font-medium text-ink">{pending.question}</p>
      {pending.choices && pending.choices.length > 0 ? (
        <div className="mt-2 flex flex-wrap gap-2">
          {pending.choices.map((c) => (
            <button
              key={c}
              onClick={() => submit(c)}
              disabled={streaming}
              className="rounded-md border border-accent px-3 py-1 text-sm text-accent hover:bg-accent hover:text-white disabled:opacity-50"
            >
              {c}
            </button>
          ))}
        </div>
      ) : (
        <div className="mt-2 flex gap-2">
          <input
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                submit(answer);
              }
            }}
            placeholder="답변을 입력하세요…"
            className="flex-1 rounded-md border border-paper-dark bg-white p-2 text-sm outline-none"
          />
          <button
            onClick={() => submit(answer)}
            disabled={streaming}
            className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-dark disabled:opacity-50"
          >
            답변
          </button>
        </div>
      )}
    </div>
  );
}
