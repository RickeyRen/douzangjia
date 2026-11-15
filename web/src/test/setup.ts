import "@testing-library/jest-dom/vitest";

// Node 25+ ships its own Web Storage globals; without a backing file they are
// unusable and shadow jsdom's, so every test touching localStorage failed.
const dom = (globalThis as { jsdom?: { window: Window } }).jsdom;
if (dom && typeof globalThis.localStorage?.clear !== "function") {
  for (const key of ["localStorage", "sessionStorage"] as const) {
    Object.defineProperty(globalThis, key, { value: dom.window[key], configurable: true });
  }
}
