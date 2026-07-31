import type { Session } from "../../types";

interface Props {
  sessions: Session[];
  activeId: string | null;
  onSelect: (id: string) => void;
}

export default function SessionList({ sessions, activeId, onSelect }: Props) {
  return (
    <ul className="mt-2 flex flex-col gap-1 overflow-y-auto">
      {sessions.map((s) => (
        <li key={s.id}>
          <button
            onClick={() => onSelect(s.id)}
            className={`w-full truncate rounded-md px-3 py-2 text-left text-sm hover:bg-paper-dark ${
              s.id === activeId ? "bg-paper-dark font-medium" : ""
            }`}
          >
            {s.title}
          </button>
        </li>
      ))}
    </ul>
  );
}
