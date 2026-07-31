import { render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import ArtifactsPanel from "./ArtifactsPanel";
import { useStore } from "../../store/store";

afterEach(() => useStore.setState({ artifactsOpen: false }));

test("hidden when artifactsOpen is false", () => {
  render(<ArtifactsPanel />);
  expect(screen.queryByTestId("artifacts-panel")).toBeNull();
});

test("visible when artifactsOpen is true", () => {
  useStore.setState({ artifactsOpen: true });
  render(<ArtifactsPanel />);
  expect(screen.getByTestId("artifacts-panel")).toBeInTheDocument();
});
