import ModeToggle from "./ModeToggle";
import MessageList from "./MessageList";
import Composer from "./Composer";
import InterruptPrompt from "./InterruptPrompt";
import { useStore } from "../../store/store";

export default function ChatPanel() {
  const messages = useStore((s) => s.messages);
  const streaming = useStore((s) => s.streaming);
  return (
    <div className="flex h-full flex-1 flex-col">
      <div className="flex items-center justify-between border-b border-paper-dark p-3">
        <ModeToggle />
      </div>
      <MessageList messages={messages} streaming={streaming} />
      <InterruptPrompt />
      <Composer />
    </div>
  );
}
