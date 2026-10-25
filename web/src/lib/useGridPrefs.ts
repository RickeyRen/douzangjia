import { useCallback, useSyncExternalStore } from "react";

export type GridDensity = "comfortable" | "compact";
export type GridAspect = "crop" | "natural";
export type GridPrefs = { density: GridDensity; aspect: GridAspect };

const KEY = "douzangjia.grid.v1";
const DEFAULT: GridPrefs = { density: "comfortable", aspect: "crop" };
const listeners = new Set<() => void>();
let cached: GridPrefs | null = null;

function read(): GridPrefs {
  if (cached) return cached;
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) ?? "null") as Partial<GridPrefs> | null;
    cached = {
      density: raw?.density === "compact" ? "compact" : "comfortable",
      aspect: raw?.aspect === "natural" ? "natural" : "crop",
    };
  } catch {
    cached = DEFAULT;
  }
  return cached;
}

export function setGridPrefs(patch: Partial<GridPrefs>) {
  cached = { ...read(), ...patch };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(cached));
  } catch {
    // Preference still applies for this session.
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useGridPrefs(): [GridPrefs, (patch: Partial<GridPrefs>) => void] {
  const prefs = useSyncExternalStore(subscribe, read, () => DEFAULT);
  const update = useCallback((patch: Partial<GridPrefs>) => setGridPrefs(patch), []);
  return [prefs, update];
}

/** Reset for tests. */
export function _resetGridPrefs() {
  cached = null;
}
