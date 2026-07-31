import { useStore } from "../../store/store";
import TraceView from "./TraceView";

export default function ArtifactsPanel() {
  const artifactsOpen = useStore((s) => s.artifactsOpen);
  const artifact = useStore((s) => s.currentArtifact);
  const traceCount = useStore((s) => s.trace.length);
  if (!artifactsOpen) return null;
  return (
    <aside
      data-testid="artifacts-panel"
      className="flex h-full w-80 flex-col overflow-y-auto border-l border-paper-dark bg-paper p-4"
    >
      <h2 className="text-sm font-semibold text-ink">Artifacts</h2>

      {artifact && (
        <div className="mt-4 rounded-md border border-paper-dark bg-white p-3">
          <p className="text-sm font-medium text-ink">{artifact.filename}</p>
          <p className="mt-1 text-xs text-ink/60">슬라이드 {artifact.slide_count}장</p>
          <a
            data-testid="artifact-download"
            href={artifact.download_url}
            download={artifact.filename}
            className="mt-3 inline-block rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:bg-accent-dark"
          >
            다운로드
          </a>
        </div>
      )}

      <TraceView />

      {!artifact && traceCount === 0 && (
        <p className="mt-4 text-sm text-ink/60">
          아직 표시할 artifact가 없습니다. PPT를 생성하면 실행 과정과 다운로드 링크가 여기에 나타납니다.
        </p>
      )}
    </aside>
  );
}
