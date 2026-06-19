import Sidebar from "./components/Sidebar/Sidebar";
import TopBar from "./components/TopBar";
import ChatPanel from "./components/Chat/ChatPanel";
import ArtifactsPanel from "./components/Artifacts/ArtifactsPanel";

export default function App() {
  return (
    <div className="flex h-screen bg-paper text-ink">
      <Sidebar />
      <main className="flex flex-1 flex-col">
        <TopBar />
        <ChatPanel />
      </main>
      <ArtifactsPanel />
    </div>
  );
}
