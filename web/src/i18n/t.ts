/**
 * gettext-style translation: the Chinese source text is the key, so untranslated
 * strings simply show as written and a catalog is a flat map of sentences.
 */
import { en } from "./catalog.en";

export type Locale = "zh-CN" | "en";
const STORAGE_KEY = "douzangjia.locale";
let current: Locale = readLocale();

function readLocale(): Locale {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "en" ? "en" : "zh-CN";
  } catch {
    return "zh-CN";
  }
}

export function currentLocale(): Locale {
  return current;
}

/** Persist and apply; callers reload so every module-level constant re-reads. */
export function setLocale(locale: Locale) {
  current = locale;
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // Still applies for this session.
  }
  document.documentElement.lang = locale;
}

export function t(text: string, vars?: Record<string, string | number>): string {
  const translated = current === "en" ? (en[text] ?? text) : text;
  if (!vars) return translated;
  return translated.replace(/\{(\w+)\}/g, (match, key: string) => (key in vars ? String(vars[key]) : match));
}

/** For tests. */
export function _setLocaleForTests(locale: Locale) {
  current = locale;
}
