import { checkOllama } from "../../api/client";
import { useStore } from "../../store/store";

export default function OllamaTestButton() {
  const ollama = useStore((s) => s.ollama);
  const setOllama = useStore((s) => s.setOllama);

  const dotClass =
    ollama == null ? "bg-gray-400" : ollama.ok ? "bg-green-500" : "bg-red-500";

  const onTest = async () => {
    try {
      setOllama(await checkOllama());
    } catch (e) {
      setOllama({ ok: false, models: [], error: String(e) });
    }
  };

  return (
    <button
      onClick={onTest}
      title={ollama?.error ?? ollama?.models.join(", ") ?? "미확인"}
      className="flex items-center gap-2 w-full rounded-md px-3 py-2 text-sm hover:bg-paper-dark"
    >
      <span data-testid="ollama-status" className={`h-2.5 w-2.5 rounded-full ${dotClass}`} />
      Ollama 연결 테스트
    </button>
  );
}
