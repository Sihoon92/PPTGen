import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import ChatPanel from "./ChatPanel";
import { useStore } from "../../store/store";
import * as sse from "../../api/sse";
import * as client from "../../api/client";

beforeEach(() => {
  useStore.setState({
    messages: [],
    mode: "chat",
    streaming: false,
    activeSessionId: "s1",
    sessions: [{ id: "s1", title: "New chat", mode: "chat", created_at: "", updated_at: "" }],
  });
});
afterEach(() => vi.restoreAllMocks());

test("sending a message streams assistant deltas into the thread", async () => {
  vi.spyOn(sse, "streamChat").mockImplementation(async (_sid, _content, _mode, h) => {
    h.onToken("Hi ");
    h.onToken("there");
    h.onDone();
  });

  render(<ChatPanel />);
  await userEvent.type(screen.getByRole("textbox"), "hello");
  await userEvent.click(screen.getByRole("button", { name: /전송/ }));

  await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
  await waitFor(() => expect(screen.getByText("Hi there")).toBeInTheDocument());
});

test("mode toggle switches active mode", async () => {
  render(<ChatPanel />);
  await userEvent.click(screen.getByRole("button", { name: "PPT" }));
  expect(useStore.getState().mode).toBe("ppt");
});

test("onDone refreshes session list so auto-title appears in sidebar", async () => {
  const renamedSession = { id: "s1", title: "My first message", mode: "chat", created_at: "2024-01-01", updated_at: "2024-01-01" };

  vi.spyOn(sse, "streamChat").mockImplementation(async (_sid, _content, _mode, h) => {
    h.onToken("Hello");
    h.onDone();
  });
  const listSpy = vi
    .spyOn(client, "listSessions")
    .mockResolvedValue([renamedSession]);

  render(<ChatPanel />);
  await userEvent.type(screen.getByRole("textbox"), "hi there");

  await act(async () => {
    await userEvent.click(screen.getByRole("button", { name: /전송/ }));
  });

  await waitFor(() => expect(listSpy).toHaveBeenCalledTimes(1));
  await waitFor(() =>
    expect(useStore.getState().sessions[0].title).toBe("My first message"),
  );
});
