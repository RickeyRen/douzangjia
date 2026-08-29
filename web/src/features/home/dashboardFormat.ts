import { formatBytes } from "../status/downloadFormat";

export function formatDelta(
  deltaBytes: number,
  comparisonAvailable: boolean,
  unavailableLabel: string,
): string {
  if (!comparisonAvailable) return unavailableLabel;
  const sign = deltaBytes > 0 ? "+" : deltaBytes < 0 ? "-" : "";
  return `${sign}${formatBytes(Math.abs(deltaBytes))}`;
}

export function formatLoadAverage(one: number, five: number, fifteen: number): string {
  return `${one.toFixed(2)} / ${five.toFixed(2)} / ${fifteen.toFixed(2)}`;
}

export function formatPercent(value: number, total: number): string {
  if (value <= 0 || total <= 0) return "0%";
  const share = (value / total) * 100;
  if (share < 0.1) return "<0.1%";
  if (share < 10) return `${share.toFixed(1)}%`;
  return `${Math.round(share)}%`;
}

export function formatRuntimeStatus(
  status: string,
  labels: Record<"running" | "busy" | "unavailable", string>,
): string {
  if (status === "running" || status === "busy") return labels[status];
  return labels.unavailable;
}

export function formatUptime(seconds: number, dayLabel: string, hourLabel: string): string {
  const days = Math.floor(Math.max(seconds, 0) / 86_400);
  const hours = Math.floor((Math.max(seconds, 0) % 86_400) / 3600);
  return days > 0 ? `${days}${dayLabel} ${hours}${hourLabel}` : `${hours}${hourLabel}`;
}
