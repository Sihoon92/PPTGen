import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import Sidebar from "./Sidebar";
import { useStore } from "../../store/store";
import * as client from "../../api/client";

afterEach(() => {
  vi.restoreAllMocks();
  useStore.setState({ sessions: [], activeSessionId: null });
});

test("loads and renders sessions on mount", async () => {
  vi.spyOn(client, "listSessions").mockResolvedValue([
    { id: "1", title: "Alpha", mode: "chat", created_at: "", updated_at: "" },
  ]);
  render(<Sidebar />);
  expect(await screen.findByText("Alpha")).toBeInTheDocument();
});

test("new session button creates and selects a session", async () => {
  vi.spyOn(client, "listSessions").mockResolvedValue([]);
  vi.spyOn(client, "createSession").mockResolvedValue({
    id: "new", title: "New chat", mode: "chat", created_at: "", updated_at: "",
  });
  render(<Sidebar />);
  await userEvent.click(screen.getByRole("button", { name: /새 세션/ }));
  await waitFor(() => expect(useStore.getState().activeSessionId).toBe("new"));
});

test("ollama test button shows green dot on success", async () => {
  vi.spyOn(client, "listSessions").mockResolvedValue([]);
  vi.spyOn(client, "checkOllama").mockResolvedValue({ ok: true, models: ["gemma3n:e4b"], error: null });
  render(<Sidebar />);
  await userEvent.click(screen.getByRole("button", { name: /Ollama 연결 테스트/ }));
  await waitFor(() =>
    expect(screen.getByTestId("ollama-status").className).toContain("bg-green-500"),
  );
});
