import { useStore } from "../../store/store";

export default function ArtifactsPanel() {
  const artifactsOpen = useStore((s) => s.artifactsOpen);
  if (!artifactsOpen) return null;
  return (
    <aside
      data-testid="artifacts-panel"
      className="flex h-full w-80 flex-col border-l border-paper-dark bg-paper p-4"
    >
      <h2 className="text-sm font-semibold text-ink">Artifacts</h2>
      <p className="mt-4 text-sm text-ink/60">
        아직 표시할 artifact가 없습니다. PPT 기능이 추가되면 여기에 미리보기가 나타납니다.
      </p>
    </aside>
  );
}
