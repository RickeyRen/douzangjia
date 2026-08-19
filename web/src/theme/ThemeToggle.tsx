import { Moon, Sun } from "@phosphor-icons/react";

import { FriendlyIconButton } from "../components/FriendlyIconButton";
import { useI18n } from "../i18n/context";
import { useTheme } from "./theme-context";

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const { t } = useI18n();
  const isLight = theme === "light";
  const label = isLight ? t("switchToDarkTheme") : t("switchToLightTheme");

  return (
    <FriendlyIconButton
      className={`theme-toggle ${className}`.trim()}
      label={label}
      aria-pressed={isLight}
      onClick={toggleTheme}
    >
      {isLight ? <Moon size={18} weight="regular" /> : <Sun size={18} weight="regular" />}
    </FriendlyIconButton>
  );
}
