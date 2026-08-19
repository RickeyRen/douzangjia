import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { I18nProvider } from "../i18n/context";
import { ThemeProvider } from "./ThemeProvider";
import { ThemeToggle } from "./ThemeToggle";

const THEME_STORAGE_KEY = "liuying.theme.v1";

function renderThemeControl() {
  return render(
    <ThemeProvider>
      <I18nProvider>
        <ThemeToggle />
      </I18nProvider>
    </ThemeProvider>,
  );
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
    delete document.documentElement.dataset.theme;
  });

  it("uses dark by default and exposes the next theme action", () => {
    renderThemeControl();

    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(screen.getByRole("button", { name: "切换到亮色主题" })).toBeInTheDocument();
  });

  it("switches to light and persists the choice", async () => {
    const user = userEvent.setup();
    renderThemeControl();

    await user.click(screen.getByRole("button", { name: "切换到亮色主题" }));

    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(screen.getByRole("button", { name: "切换到暗色主题" })).toBeInTheDocument();
  });

  it("restores a stored light theme on mount", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");

    renderThemeControl();

    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(screen.getByRole("button", { name: "切换到暗色主题" })).toBeInTheDocument();
  });
});
