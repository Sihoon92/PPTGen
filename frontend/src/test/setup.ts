import "@testing-library/jest-dom";

// Suppress known act() warnings from async Zustand state updates in useEffect.
// RTL tests use findBy/waitFor which correctly await async effects; the warning
// is a false positive caused by Zustand's external state triggering re-renders
// outside of RTL's initial render act() scope.
const originalError = console.error.bind(console);
console.error = (...args: unknown[]) => {
  const msg = typeof args[0] === "string" ? args[0] : "";
  if (msg.includes("not wrapped in act(")) return;
  originalError(...args);
};
