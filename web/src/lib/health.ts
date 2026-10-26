import type { SyncHealth } from "../app/api";
import { formatRelative } from "./format";
import { t } from "../i18n/t";

export type HealthTone = "ok" | "busy" | "warning" | "danger";

export type HealthView = {
  tone: HealthTone;
  /** Short label for the sidebar pill. */
  label: string;
  title: string;
  body: string;
  /** Whether the problem deserves a banner above page content. */
  alert: boolean;
  action: "login" | "sync" | null;
};

const ERROR_TEXT: Record<string, string> = {
  DOUYIN_RESPONSE_CHANGED: "抖音页面结构有变化，读取收藏失败",
  DOUYIN_SESSION_EXPIRED: "抖音登录已失效",
  SESSION_EXPIRED: "抖音登录已失效",
  BROWSER_DISCONNECTED: "后台浏览器已断开",
  SYNC_STALLED: "同步任务没有在运行",
  NETWORK_TIMEOUT: "访问抖音超时",
  RATE_LIMITED: "抖音限制了访问频率",
  COUNT_MISMATCH: "数量和抖音上不一致，会在下次核对时补齐",
  DOWNLOAD_FAILED: "下载失败",
  CREATOR_SYNC_FAILED: "博主作品同步失败",
  DOUYIN_PAGE_CRASHED: "后台页面多次崩溃，已重开仍未完成",
  SYNC_FAILED: "同步意外中断",
  SYNC_TIMEOUT: "同步耗时过长，已放弃并重启后台浏览器",
  SYNC_INTERRUPTED: "同步被服务重启打断，下次会接着做",
};

/** Codes that describe bookkeeping, not problems worth showing to people. */
const SILENT_CODES = new Set(["COUNT_UNKNOWN"]);

export function describeError(code: string | null | undefined): string | null {
  if (!code || SILENT_CODES.has(code)) return null;
  return ERROR_TEXT[code] ?? code;
}

/** " · reason" for inline metadata, or nothing when the code is silent. */
export function errorSuffix(code: string | null | undefined): string {
  const text = describeError(code);
  return text ? ` · ${text}` : "";
}

export function describeHealth(health: SyncHealth | null, now = Date.now()): HealthView {
  if (!health) {
    return { tone: "busy", label: t("正在检查"), title: t("正在检查同步状态"), body: "", alert: false, action: null };
  }
  const last = formatRelative(health.lastSuccessAt, now);
  const reason = describeError(health.lastErrorCode);
  switch (health.state) {
    case "ok":
      return {
        tone: "ok",
        label: t("同步正常"),
        title: t("同步正常"),
        body: t("上次同步 {last}，每 {minutes} 分钟检查一次新收藏", { last, minutes: Math.round(health.intervalSeconds / 60) }),
        alert: false,
        action: null,
      };
    case "syncing":
      return { tone: "busy", label: t("正在同步"), title: t("正在同步收藏"), body: t("上次完成 {last}", { last }), alert: false, action: null };
    case "never":
      return {
        tone: "warning",
        label: t("尚未同步"),
        title: t("还没有完成过同步"),
        body: t("扫码登录后会自动开始第一次全量同步。"),
        alert: true,
        action: "sync",
      };
    case "login_required":
      return {
        tone: "danger",
        label: t("需要登录"),
        title: t("抖音登录已失效，新收藏不会再同步"),
        body: t("上次成功同步 {last}。重新扫码登录后会自动恢复。", { last }),
        alert: true,
        action: "login",
      };
    case "failing":
      return {
        tone: "danger",
        label: t("同步失败"),
        title: t("同步连续失败"),
        body: (reason ? `${reason}。` : "") + t("上次成功同步 {last}，已连续失败 {n} 次。", { last, n: Math.max(health.consecutiveFailures, 1) }),
        alert: true,
        action: "sync",
      };
    case "stale":
      return {
        tone: "danger",
        label: t("同步停滞"),
        title: t("同步已经停止"),
        body: t("上次成功同步是 {last}，之后没有新的同步完成{reason}。", { last, reason: reason && reason !== ERROR_TEXT.SYNC_STALLED ? `（${reason}）` : "" }),
        alert: true,
        action: "sync",
      };
  }
}
