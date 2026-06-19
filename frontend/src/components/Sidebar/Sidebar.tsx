import { useEffect, useRef, useState } from "react";
import { createSession, getMessages, listSessions } from "../../api/client";
import { useStore } from "../../store/store";
import OllamaTestButton from "./OllamaTestButton";
import SessionList from "./SessionList";

export default function Sidebar() {
  const [sessions, setSessions] = useState(useStore.getState().sessions);
  const [activeSessionId, setActiveSessionId] = useState(
    useStore.getState().activeSessionId,
  );
  const mountedRef = useRef(false);

  const refresh = async () => {
    const data = await listSessions();
    if (mountedRef.current) {
      useStore.getState().setSessions(data);
      setSessions(data);
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    refresh();
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const onNew = async () => {
    const session = await createSession();
    await refresh();
    useStore.getState().setActiveSession(session.id);
    useStore.getState().setMessages([]);
    setActiveSessionId(session.id);
  };

  const onSelect = async (id: string) => {
    useStore.getState().setActiveSession(id);
    setActiveSessionId(id);
    useStore.getState().setMessages((await getMessages(id)).messages);
  };

  return (
    <aside className="flex h-full w-64 flex-col border-r border-paper-dark bg-paper p-3">
      <button
        onClick={onNew}
        className="rounded-md bg-accent px-3 py-2 text-sm font-medium text-white hover:bg-accent-dark"
      >
        + 새 세션
      </button>
      <div className="mt-2">
        <OllamaTestButton />
      </div>
      <hr className="my-2 border-paper-dark" />
      <SessionList sessions={sessions} activeId={activeSessionId} onSelect={onSelect} />
    </aside>
  );
}
