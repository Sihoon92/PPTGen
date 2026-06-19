import ModeToggle from "./ModeToggle";
import MessageList from "./MessageList";
import Composer from "./Composer";
import { useStore } from "../../store/store";

export default function ChatPanel() {
  const messages = useStore((s) => s.messages);
  return (
    <div className="flex h-full flex-1 flex-col">
      <div className="flex items-center justify-between border-b border-paper-dark p-3">
        <ModeToggle />
      </div>
      <MessageList messages={messages} />
      <Composer />
    </div>
  );
}
