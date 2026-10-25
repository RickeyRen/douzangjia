import { currentLocale } from "../i18n/t";

const integer = new Intl.NumberFormat("zh-CN");
const en = () => currentLocale() === "en";

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (en()) {
    if (value >= 1_000_000) return `${trim(value / 1_000_000)}M`;
    if (value >= 10_000) return `${trim(value / 1_000)}K`;
    return integer.format(value);
  }
  if (value >= 100_000_000) return `${trim(value / 100_000_000)} 亿`;
  if (value >= 10_000) return `${trim(value / 10_000)} 万`;
  return integer.format(value);
}

export function formatInteger(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : integer.format(value);
}

function trim(value: number): string {
  return value >= 100 ? Math.round(value).toString() : value.toFixed(1).replace(/\.0$/, "");
}

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${value >= 100 || exponent === 0 ? Math.round(value) : value.toFixed(1)} ${units[exponent]}`;
}

export function formatSpeed(bytesPerSecond: number | null | undefined): string {
  return `${formatBytes(bytesPerSecond ?? 0)}/s`;
}

export function formatDuration(milliseconds: number | null | undefined): string | null {
  if (!milliseconds || milliseconds <= 0) return null;
  const total = Math.round(milliseconds / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = (total % 60).toString().padStart(2, "0");
  return hours > 0 ? `${hours}:${minutes.toString().padStart(2, "0")}:${seconds}` : `${minutes}:${seconds}`;
}

export function formatEta(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds <= 0) return "—";
  if (seconds < 60) return en() ? `${Math.round(seconds)}s` : `${Math.round(seconds)} 秒`;
  if (seconds < 3600) return en() ? `${Math.round(seconds / 60)} min` : `${Math.round(seconds / 60)} 分钟`;
  return en() ? `${(seconds / 3600).toFixed(1)} h` : `${(seconds / 3600).toFixed(1)} 小时`;
}

/** Relative time in Chinese for unix seconds, e.g. "3 分钟前", "29 天前". */
export function formatRelative(unixSeconds: number | null | undefined, now = Date.now()): string {
  if (!unixSeconds) return en() ? "never" : "从未";
  const delta = Math.round(now / 1000 - unixSeconds);
  if (delta < 45) return en() ? "just now" : "刚刚";
  if (delta < 3600) {
    const minutes = Math.max(1, Math.round(delta / 60));
    return en() ? `${minutes} min ago` : `${minutes} 分钟前`;
  }
  if (delta < 86_400) {
    const hours = Math.round(delta / 3600);
    return en() ? `${hours} h ago` : `${hours} 小时前`;
  }
  if (delta < 86_400 * 30) {
    const days = Math.round(delta / 86_400);
    return en() ? `${days} d ago` : `${days} 天前`;
  }
  return formatDate(unixSeconds);
}

export function formatDate(unixSeconds: number | null | undefined): string {
  if (!unixSeconds) return "—";
  const date = new Date(unixSeconds * 1000);
  if (en()) return date.toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

export function formatDateTime(unixSeconds: number | null | undefined): string {
  if (!unixSeconds) return "—";
  const date = new Date(unixSeconds * 1000);
  const time = `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;
  if (en()) return `${date.toLocaleDateString("en-US", { month: "short", day: "numeric" })} ${time}`;
  return `${date.getMonth() + 1}月${date.getDate()}日 ${time}`;
}

export function greeting(now = new Date()): string {
  const hour = now.getHours();
  if (en()) return hour < 5 ? "Up late" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  if (hour < 5) return "夜深了";
  if (hour < 11) return "早上好";
  if (hour < 13) return "中午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}

/** Player clock: m:ss, or h:mm:ss past an hour. */
export function formatClock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const whole = Math.floor(seconds);
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const rest = (whole % 60).toString().padStart(2, "0");
  return hours ? `${hours}:${minutes.toString().padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}
