import { Browser, CloudArrowDown, Cpu } from "@phosphor-icons/react";

import type { DashboardRuntime } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { formatBytes, formatSpeed } from "../status/downloadFormat";
import { formatRuntimeStatus, formatUptime } from "./dashboardFormat";
import { DashboardSection } from "./DashboardPrimitives";

function timestamp(value: number | null, locale: "zh-CN" | "en"): string {
  if (value === null) return "—";
  return new Intl.DateTimeFormat(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value * 1000));
}

export function RuntimeSection({ runtime }: { runtime: DashboardRuntime }) {
  const { t, locale } = useI18n();
  const labels = { running: t("runtimeRunning"), busy: t("runtimeBusy"), unavailable: t("runtimeUnavailable") };
  const cards = [
    {
      id: "application",
      tone: "blue",
      title: t("applicationService"),
      icon: <Cpu size={17} weight="duotone" />,
      status: runtime.application.status,
      metrics: [
        [t("processMemory"), formatBytes(runtime.application.memoryBytes)],
        [t("cpuUsage"), `${runtime.application.cpuLoadPercent.toFixed(1)}%`],
        [t("serviceUptime"), formatUptime(runtime.application.uptimeSeconds, t("dayShort"), t("hourShort"))],
        [t("lastActivity"), timestamp(runtime.application.lastActivityAt, locale)],
      ],
    },
    {
      id: "downloader",
      tone: "violet",
      title: t("downloadEngine"),
      icon: <CloudArrowDown size={17} weight="duotone" />,
      status: runtime.downloader.status,
      metrics: [
        [t("workerStatus"), `${runtime.downloader.activeWorkers} / ${runtime.downloader.workerCount}`],
        [t("activeDownloads"), String(runtime.downloader.activeDownloads)],
        [t("pendingWork"), String(runtime.downloader.pendingDownloads)],
        [t("currentSpeed"), formatSpeed(runtime.downloader.speedBps)],
        [t("lastActivity"), timestamp(runtime.downloader.lastActivityAt, locale)],
      ],
    },
    {
      id: "browser",
      tone: "green",
      title: t("syncBrowser"),
      icon: <Browser size={17} weight="duotone" />,
      status: runtime.browser.status,
      metrics: [
        [t("processCount"), `${runtime.browser.processCount} ${t("processUnit")}`],
        [t("browserMemory"), formatBytes(runtime.browser.memoryBytes)],
        [t("browserLease"), runtime.browser.busy ? t("runtimeBusy") : t("runtimeIdle")],
        [t("lastActivity"), timestamp(runtime.browser.lastActivityAt, locale)],
      ],
    },
  ] as const;
  return (
    <DashboardSection title="Runtime" className="home-runtime-section">
      <div className="home-runtime-grid">
        {cards.map((card) => (
          <article key={card.id} className="home-runtime-card" data-runtime-tone={card.tone}>
            <header><span className="app-icon-well" data-icon-tone={card.tone}>{card.icon}</span><strong>{card.title}</strong><small>{formatRuntimeStatus(card.status, labels)}</small></header>
            <dl>{card.metrics.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
          </article>
        ))}
      </div>
    </DashboardSection>
  );
}
