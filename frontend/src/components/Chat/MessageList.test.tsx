import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import MessageList from "./MessageList";
import type { ChatMessage } from "../../types";

afterEach(() => vi.restoreAllMocks());

const assistant = (content: string): ChatMessage => ({ role: "assistant", content });

test("renders a markdown table as a real <table>", () => {
  const md = "| 항목 | 값 |\n| - | - |\n| 속도 | 빠름 |";
  render(<MessageList messages={[assistant(md)]} streaming={false} />);
  expect(screen.getByRole("table")).toBeInTheDocument();
  expect(screen.getByText("항목")).toBeInTheDocument();
  expect(screen.getByText("빠름")).toBeInTheDocument();
});

test("renders bold markdown as <strong>", () => {
  render(<MessageList messages={[assistant("이건 **굵게** 입니다")]} streaming={false} />);
  expect(screen.getByText("굵게").tagName).toBe("STRONG");
});

test("renders a mermaid code block via the mermaid engine", async () => {
  const md = "```mermaid\nflowchart TD\n  A --> B\n```";
  render(<MessageList messages={[assistant(md)]} streaming={false} />);
  expect(await screen.findByTestId("mermaid-svg")).toBeInTheDocument();
});

test("shows the loading indicator for an empty assistant message while streaming", () => {
  render(
    <MessageList
      messages={[{ role: "user", content: "hi" }, assistant("")]}
      streaming={true}
    />,
  );
  expect(screen.getByRole("status", { name: "생각 중" })).toBeInTheDocument();
});

test("no loading indicator once content is present / not streaming", () => {
  render(<MessageList messages={[assistant("완료")]} streaming={false} />);
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.getByText("완료")).toBeInTheDocument();
});

test("user messages render as plain text (markdown not parsed)", () => {
  render(
    <MessageList messages={[{ role: "user", content: "**not bold**" }]} streaming={false} />,
  );
  // user 말풍선은 평문이라 ** 가 그대로 보이고 <strong> 으로 변환되지 않는다.
  expect(screen.getByText("**not bold**")).toBeInTheDocument();
});
