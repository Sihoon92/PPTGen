import { render } from "@testing-library/react";
import App from "./App";

test("renders app shell with paper background", () => {
  const { container } = render(<App />);
  const root = container.firstChild as HTMLElement;
  expect(root.className).toContain("bg-paper");
});
