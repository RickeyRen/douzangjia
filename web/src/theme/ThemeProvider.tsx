import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { ThemeContext, type Theme, type ThemePreference } from "./theme-context";

const THEME_STORAGE_KEY = "liuying.theme.v1";
const THEME_COLORS: Record<Theme, string> = { dark: "#0b0b0d", light: "#f5f5f3" };

function readPreference(): ThemePreference {
  if (typeof window === "undefined") return "dark";
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    return stored === "light" || stored === "system" ? stored : "dark";
  } catch {
    return "dark";
  }
}

function systemTheme(): Theme {
  if (typeof window === "undefined" || !window.matchMedia) return "dark";
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreference] = useState<ThemePreference>(readPreference);
  const [system, setSystem] = useState<Theme>(systemTheme);
  const theme: Theme = preference === "system" ? system : preference;

  useEffect(() => {
    if (preference !== "system" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-color-scheme: light)");
    const update = () => setSystem(query.matches ? "light" : "dark");
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, [preference]);

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", THEME_COLORS[theme]);
  }, [theme]);

  useEffect(() => {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, preference);
    } catch {
      // The selected theme still applies when storage is unavailable.
    }
  }, [preference]);

  const setTheme = useCallback((next: Theme) => setPreference(next), []);
  const toggleTheme = useCallback(() => setPreference(theme === "dark" ? "light" : "dark"), [theme]);

  const value = useMemo(
    () => ({ theme, preference, setTheme, setPreference, toggleTheme }),
    [preference, setTheme, theme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
