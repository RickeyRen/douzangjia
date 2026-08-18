import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { en } from "./en";
import { zhCN } from "./zh-CN";

type Locale = "zh-CN" | "en";
type Key = keyof typeof zhCN;

const I18nContext = createContext<{
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: Key) => string;
} | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>("zh-CN");
  const value = useMemo(() => {
    const resources = locale === "zh-CN" ? zhCN : en;
    return { locale, setLocale, t: (key: Key) => resources[key] };
  }, [locale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    return { locale: "zh-CN" as const, setLocale: () => undefined, t: (key: Key) => zhCN[key] };
  }
  return context;
}
