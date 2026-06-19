import { useStore } from "../store/store";

export default function TopBar() {
  const toggleArtifacts = useStore((s) => s.toggleArtifacts);
  const artifactsOpen = useStore((s) => s.artifactsOpen);
  return (
    <div className="flex items-center justify-end border-b border-paper-dark bg-paper px-4 py-2">
      <button
        onClick={toggleArtifacts}
        className={`rounded-md border border-paper-dark px-3 py-1 text-sm ${
          artifactsOpen ? "bg-accent text-white" : "text-ink"
        }`}
      >
        Artifacts {artifactsOpen ? "▣" : "▢"}
      </button>
    </div>
  );
}
