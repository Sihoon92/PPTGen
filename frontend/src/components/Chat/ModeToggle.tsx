import type { Mode } from "../../types";
import { useStore } from "../../store/store";

const MODES: Mode[] = ["chat", "ppt"];

export default function ModeToggle() {
  const mode = useStore((s) => s.mode);
  const setMode = useStore((s) => s.setMode);
  return (
    <div className="flex gap-1 rounded-lg bg-paper-dark p-1">
      {MODES.map((m) => (
        <button
          key={m}
          onClick={() => setMode(m)}
          className={`rounded-md px-3 py-1 text-sm capitalize ${
            mode === m ? "bg-accent text-white" : "text-ink"
          }`}
        >
          {m === "chat" ? "Chat" : "PPT"}
        </button>
      ))}
    </div>
  );
}
