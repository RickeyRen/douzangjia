export function formatBytes(value: number): string {
  const safeValue = Math.max(0, value);
  if (safeValue < 1024) return `${Math.round(safeValue)} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let amount = safeValue / 1024;
  let index = 0;
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024;
    index += 1;
  }
  return `${amount.toFixed(1)} ${units[index]}`;
}

export function formatSpeed(value: number): string {
  return `${formatBytes(value)}/s`;
}

export function formatEta(value: number | null, locale: "zh-CN" | "en"): string {
  if (value === null) return "—";
  if (value <= 0) return locale === "zh-CN" ? "即将完成" : "finishing";
  if (value < 60) return locale === "zh-CN" ? `约 ${Math.ceil(value)} 秒` : `about ${Math.ceil(value)} sec`;
  if (value < 3600) {
    const minutes = Math.max(1, Math.round(value / 60));
    return locale === "zh-CN" ? `约 ${minutes} 分钟` : `about ${minutes} min`;
  }
  const hours = Math.max(1, Math.round(value / 3600));
  return locale === "zh-CN" ? `约 ${hours} 小时` : `about ${hours} hr`;
}

export function formatDateTime(value: number | null, locale: "zh-CN" | "en"): string {
  if (value === null) return "—";
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value * 1000));
}
