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

test("buffers tokens: shows loading and no partial text until done, then full content", async () => {
  let finish!: () => void;
  vi.spyOn(sse, "streamChat").mockImplementation((_s, _c, _m, h) => {
    h.onToken("부분");
    h.onToken(" 텍스트");
    return new Promise<void>((resolve) => {
      finish = () => {
        h.onDone();
        resolve();
      };
    });
  });

  render(<ChatPanel />);
  await userEvent.type(screen.getByRole("textbox"), "hi");
  await userEvent.click(screen.getByRole("button", { name: /전송/ }));

  // 아직 onDone 전: 로딩 인디케이터 표시, 부분 텍스트는 화면에 없음.
  await waitFor(() =>
    expect(screen.getByRole("status", { name: "생각 중" })).toBeInTheDocument(),
  );
  expect(screen.queryByText(/부분 텍스트/)).toBeNull();

  // onDone 후: 전체 내용이 한 번에 표시되고 로딩은 사라짐.
  await act(async () => {
    finish();
  });
  await waitFor(() => expect(screen.getByText(/부분 텍스트/)).toBeInTheDocument());
  expect(screen.queryByRole("status")).toBeNull();
});

test("sending with no active session auto-creates one then streams", async () => {
  useStore.setState({ activeSessionId: null, sessions: [] });
  const createSpy = vi.spyOn(client, "createSession").mockResolvedValue({
    id: "auto", title: "New chat", mode: "chat", created_at: "", updated_at: "",
  });
  vi.spyOn(client, "listSessions").mockResolvedValue([]);
  vi.spyOn(sse, "streamChat").mockImplementation(async (sid, _content, _mode, h) => {
    expect(sid).toBe("auto"); // streams against the freshly created session
    h.onToken("yo");
    h.onDone();
  });

  render(<ChatPanel />);
  await userEvent.type(screen.getByRole("textbox"), "hello");
  await act(async () => {
    await userEvent.click(screen.getByRole("button", { name: /전송/ }));
  });

  await waitFor(() => expect(createSpy).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(useStore.getState().activeSessionId).toBe("auto"));
  await waitFor(() => expect(screen.getByText("yo")).toBeInTheDocument());
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
