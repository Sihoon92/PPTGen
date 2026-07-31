import { beforeEach, expect, test } from "vitest";
import { useStore } from "./store";

beforeEach(() => {
  useStore.setState({
    sessions: [], activeSessionId: null, messages: [],
    mode: "chat", artifactsOpen: false, ollama: null, streaming: false,
  });
});

test("appendUserMessage adds a user message", () => {
  useStore.getState().appendUserMessage("hi");
  expect(useStore.getState().messages).toEqual([{ role: "user", content: "hi" }]);
});

test("assistant streaming accumulates deltas", () => {
  const s = useStore.getState();
  s.startAssistantMessage();
  s.appendAssistantDelta("He");
  s.appendAssistantDelta("llo");
  const msgs = useStore.getState().messages;
  expect(msgs[msgs.length - 1]).toEqual({ role: "assistant", content: "Hello" });
});

test("setLastAssistantContent sets (not appends) the last assistant message", () => {
  const s = useStore.getState();
  s.startAssistantMessage();
  s.appendAssistantDelta("ignored buffer");
  useStore.getState().setLastAssistantContent("final content");
  const msgs = useStore.getState().messages;
  expect(msgs[msgs.length - 1]).toEqual({ role: "assistant", content: "final content" });
});

test("toggleArtifacts flips the flag", () => {
  useStore.getState().toggleArtifacts();
  expect(useStore.getState().artifactsOpen).toBe(true);
});

test("setMode updates mode", () => {
  useStore.getState().setMode("ppt");
  expect(useStore.getState().mode).toBe("ppt");
});
