import { render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";
import * as client from "./api/client";

afterEach(() => vi.restoreAllMocks());

test("renders app shell with paper background", () => {
  vi.spyOn(client, "listSessions").mockResolvedValue([]);
  const { container } = render(<App />);
  const root = container.firstChild as HTMLElement;
  expect(root.className).toContain("bg-paper");
});
