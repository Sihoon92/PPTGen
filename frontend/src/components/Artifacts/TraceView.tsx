import { useState } from "react";
import { useStore } from "../../store/store";

const ICON: Record<string, string> = { running: "🔄", done: "✅", error: "❌" };

// Live debug view of the PPT subgraph: which node ran, with which tool, and what
// it produced. Each row expands to the raw output JSON. A link downloads the full
// persisted trace for the session.
export default function TraceView() {
  const trace = useStore((s) => s.trace);
  const activeSessionId = useStore((s) => s.activeSessionId);
  const [open, setOpen] = useState<Record<string, boolean>>({});

  if (trace.length === 0) return null;

  return (
    <div className="mt-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-ink/60">실행 추적</h3>
        {activeSessionId && (
          <a
            data-testid="trace-download"
            href={`/api/sessions/${activeSessionId}/trace`}
            download="trace.json"
            className="text-xs text-accent hover:underline"
          >
            JSON
          </a>
        )}
      </div>
      <ol data-testid="trace-list" className="mt-2 space-y-1">
        {trace.map((e) => {
          const key = `${e.node}-${e.step}`;
          const expanded = open[key];
          return (
            <li key={key} className="overflow-hidden rounded border border-paper-dark bg-white">
              <button
                onClick={() => setOpen((o) => ({ ...o, [key]: !o[key] }))}
                className="flex w-full items-center gap-2 p-2 text-left text-xs"
              >
                <span>{ICON[e.status] ?? "•"}</span>
                <span className="font-medium text-ink">{e.label}</span>
                {e.tool && (
                  <span className="rounded bg-paper px-1 text-[10px] text-ink/50">{e.tool}</span>
                )}
                <span className="ml-auto max-w-[8rem] truncate text-ink/60">{e.summary}</span>
              </button>
              {expanded && e.output !== undefined && (
                <pre className="max-h-60 overflow-auto border-t border-paper-dark bg-paper p-2 text-[10px] leading-tight text-ink/80">
                  {JSON.stringify(e.output, null, 2)}
                </pre>
              )}
              {e.error && (
                <p className="border-t border-paper-dark p-2 text-[10px] text-red-600">{e.error}</p>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
