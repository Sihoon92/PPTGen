import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import ChatPanel from "./ChatPanel";
import { useStore } from "../../store/store";
import * as sse from "../../api/sse";

beforeEach(() => {
  useStore.setState({ messages: [], mode: "chat", streaming: false, activeSessionId: "s1" });
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
