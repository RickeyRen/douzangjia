import {
  Browser,
  CalendarBlank,
  CheckCircle,
  CloudArrowDown,
  Cpu,
  Database,
  DownloadSimple,
  HardDrives,
  Heartbeat,
  Hourglass,
  IdentificationCard,
  Memory,
  Pulse,
  Stack,
  TiktokLogo,
  UserCircle,
  UsersThree,
  VideoCamera,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";

import { useI18n } from "../../i18n/context";
import { ThemeToggle } from "../../theme/ThemeToggle";
import { formatBytes, formatSpeed } from "../status/downloadFormat";
import { formatDelta, formatLoadAverage, formatPercent, formatRuntimeStatus } from "./dashboardFormat";
import { DashboardMetric, DashboardSection, DashboardTrend } from "./DashboardPrimitives";
import { LiveActivitySection } from "./LiveActivitySection";
import { RuntimeSection } from "./RuntimeSection";
import { SourceProgressSection } from "./SourceProgressSection";
import { useDashboardStream, type DashboardStreamState } from "./useDashboardStream";

function timestamp(value: number | null, locale: "zh-CN" | "en"): string {
  if (value === null) return "—";
  return new Intl.DateTimeFormat(locale, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value * 1000));
}

export function HomePage({
  onOpenDownloads,
  onOpenSource,
  stream,
}: {
  onOpenDownloads: () => void;
  onOpenSource: (sourceId: string) => void;
  stream?: DashboardStreamState;
}) {
  const { t, locale } = useI18n();
  const localStream = useDashboardStream(stream === undefined);
  const { snapshot, series, connected, loading, error } = stream ?? localStream;

  if (loading && !snapshot) return <div className="home-state home-skeleton" aria-label={t("loadingStatus")} />;
  if (error && !snapshot) return <div className="home-state"><p>{t("dashboardLoadFailed")}</p></div>;
  if (!snapshot) return null;

  const number = new Intl.NumberFormat(locale);
  const account = snapshot.account.account;
  const accountName = account?.nickname ?? t("brand");
  const accountId = account?.uniqueId ?? t("creatorIdUnavailable");
  const runtimeLabels = { running: t("runtimeRunning"), busy: t("runtimeBusy"), unavailable: t("runtimeUnavailable") };
  const healthLabels = {
    healthy: t("healthHealthy"),
    degraded: t("healthDegraded"),
    expired: t("healthExpired"),
    checking: t("healthChecking"),
    unknown: t("healthUnknown"),
  };
  const totalObservedMemory = snapshot.runtime.application.memoryBytes + snapshot.runtime.browser.memoryBytes;
  const comparison = (window: typeof snapshot.throughput.today, label: string) => (
    <span className="home-metric-comparison" data-direction={window.deltaBytes > 0 ? "up" : window.deltaBytes < 0 ? "down" : "flat"}>
      <span>{formatDelta(window.deltaBytes, window.comparisonAvailable, t("dataAccumulating"))}</span>
      {window.comparisonAvailable ? <small>{label}</small> : null}
    </span>
  );

  return (
    <main className="home-page" aria-label={t("home")}>
      <header className="home-header">
        <div className="home-brand">
          <span className="app-icon-well" data-icon-tone="cyan"><TiktokLogo size={22} weight="duotone" /></span>
          <div><h1>{t("brand")}</h1><p>{t("brandSubtitle")}</p></div>
        </div>
        <div className="home-account">
          {account?.avatarUrl ? <img src={account.avatarUrl} alt="" /> : <span><UserCircle size={24} weight="duotone" /></span>}
          <div><strong>{accountName}</strong><small>{t("douyinId")} · {accountId}</small></div>
        </div>
        <div className={`home-live-state${connected ? " is-live" : ""}`}>
          <i />
          <span><strong>{t(connected ? "liveConnectedStatus" : "liveDisconnectedStatus")}</strong><small><span>{t("lastUpdated")}</span> · {timestamp(snapshot.generatedAt, locale)}</small></span>
        </div>
        <ThemeToggle />
      </header>

      <div className="home-scroll">
        <LiveActivitySection activity={snapshot.activity} speedBps={snapshot.queue.speedBps} onOpenDownloads={onOpenDownloads} />

        <DashboardSection title={t("engineUsageTitle")}>
          <div className="home-dashboard-grid is-four">
            <DashboardMetric label={t("serviceCount")} value={`${snapshot.runtime.serviceCount} ${t("serviceUnit")}`} icon={<Stack size={18} weight="duotone" />} tone="blue" />
            <DashboardMetric label={t("appAndBrowserMemory")} value={formatBytes(totalObservedMemory)} detail={`${t("processMemory")} ${formatBytes(snapshot.runtime.application.memoryBytes)}`} icon={<Memory size={18} weight="duotone" />} tone="cyan" />
            <DashboardMetric label={t("currentSpeed")} value={formatSpeed(snapshot.queue.speedBps)} detail={`${snapshot.queue.running} ${t("activeDownloads")}`} icon={<DownloadSimple size={18} weight="duotone" />} tone="amber" onClick={onOpenDownloads} />
            <DashboardMetric label={t("averageCpuLoad")} value={`${snapshot.system.cpuLoadPercent.toFixed(1)}%`} detail={formatLoadAverage(snapshot.system.loadAverage1m, snapshot.system.loadAverage5m, snapshot.system.loadAverage15m)} icon={<Cpu size={18} weight="duotone" />} tone="violet" />
          </div>
        </DashboardSection>

        <DashboardSection title={t("serviceDetailsTitle")}>
          <div className="home-dashboard-grid is-three home-service-grid">
            <DashboardMetric label={t("applicationService")} value={runtimeLabels.running} detail={formatBytes(snapshot.runtime.application.memoryBytes)} icon={<Cpu size={18} weight="duotone" />} tone="blue" />
            <DashboardMetric label={t("downloadEngine")} value={formatRuntimeStatus(snapshot.runtime.downloader.status, runtimeLabels)} detail={`${snapshot.runtime.downloader.activeWorkers} / ${snapshot.runtime.downloader.workerCount} Worker`} icon={<CloudArrowDown size={18} weight="duotone" />} tone="violet" onClick={onOpenDownloads} />
            <DashboardMetric label={t("syncBrowser")} value={formatRuntimeStatus(snapshot.runtime.browser.status, runtimeLabels)} detail={`${snapshot.runtime.browser.processCount} ${t("processUnit")} · ${formatBytes(snapshot.runtime.browser.memoryBytes)}`} icon={<Browser size={18} weight="duotone" />} tone="green" />
          </div>
        </DashboardSection>

        <DashboardSection title={t("throughputTitle")}>
          <div className="home-dashboard-grid is-four home-throughput-grid">
            <DashboardMetric label={t("today")} value={formatBytes(snapshot.throughput.today.bytes)} detail={comparison(snapshot.throughput.today, t("compareYesterday"))} icon={<CalendarBlank size={18} weight="duotone" />} tone="blue" />
            <DashboardMetric label={t("lastSevenDays")} value={formatBytes(snapshot.throughput.sevenDays.bytes)} detail={comparison(snapshot.throughput.sevenDays, t("compareLastWeek"))} icon={<CalendarBlank size={18} weight="duotone" />} tone="green" />
            <DashboardMetric label={t("lastThirtyDays")} value={formatBytes(snapshot.throughput.thirtyDays.bytes)} detail={comparison(snapshot.throughput.thirtyDays, t("comparePreviousPeriod"))} icon={<CalendarBlank size={18} weight="duotone" />} tone="amber" />
            <DashboardMetric label={t("lifetimeArchive")} value={formatBytes(snapshot.throughput.lifetime.bytes)} detail={snapshot.throughput.historyStartedAt === null ? t("dataAccumulating") : timestamp(snapshot.throughput.historyStartedAt, locale)} icon={<Database size={18} weight="duotone" />} tone="violet" />
          </div>
        </DashboardSection>

        <DashboardSection title={t("queueStatusTitle")}>
          <div className="home-dashboard-grid is-five home-queue-grid">
            <DashboardMetric label={t("statusPending")} value={number.format(snapshot.queue.pending)} icon={<Hourglass size={18} weight="duotone" />} tone="blue" onClick={onOpenDownloads} />
            <DashboardMetric label={t("statusRunning")} value={number.format(snapshot.queue.running)} detail={formatSpeed(snapshot.queue.speedBps)} icon={<DownloadSimple size={18} weight="duotone" />} tone="green" onClick={onOpenDownloads} />
            <DashboardMetric label={t("statusRetry")} value={number.format(snapshot.queue.retry)} icon={<Pulse size={18} weight="duotone" />} tone="amber" onClick={onOpenDownloads} />
            <DashboardMetric label={t("statusFailed")} value={number.format(snapshot.queue.failed)} icon={<XCircle size={18} weight="duotone" />} tone="rose" onClick={onOpenDownloads} />
            <DashboardMetric label={t("statusCompleted")} value={number.format(snapshot.queue.completed)} icon={<CheckCircle size={18} weight="duotone" />} tone="violet" onClick={onOpenDownloads} />
          </div>
        </DashboardSection>

        <DashboardSection title={t("nasSystemTitle")}>
          <div className="home-dashboard-grid is-four">
            <DashboardMetric label={t("archiveData")} value={formatBytes(snapshot.storage.archiveBytes)} detail={`${formatPercent(snapshot.storage.archiveBytes, snapshot.storage.totalBytes)} ${t("storageUsage")}`} icon={<Database size={18} weight="duotone" />} tone="blue" />
            <DashboardMetric label={t("diskSpace")} value={`${formatBytes(snapshot.storage.usedBytes)} / ${formatBytes(snapshot.storage.totalBytes)}`} detail={`${formatBytes(snapshot.storage.freeBytes)} ${t("freeStorage")}`} icon={<HardDrives size={18} weight="duotone" />} tone="cyan" />
            <DashboardMetric label={t("systemMemory")} value={`${formatBytes(snapshot.system.memoryUsedBytes)} / ${formatBytes(snapshot.system.memoryTotalBytes)}`} detail={formatPercent(snapshot.system.memoryUsedBytes, snapshot.system.memoryTotalBytes)} icon={<Memory size={18} weight="duotone" />} tone="green" />
            <DashboardMetric label={t("loadAverage")} value={formatLoadAverage(snapshot.system.loadAverage1m, snapshot.system.loadAverage5m, snapshot.system.loadAverage15m)} detail={`${snapshot.system.cpuCount} CPU`} icon={<Cpu size={18} weight="duotone" />} tone="violet" />
          </div>
        </DashboardSection>

        <DashboardSection title={t("libraryTitle")}>
          <div className="home-dashboard-grid is-five">
            <DashboardMetric label={t("discoveredItems")} value={number.format(snapshot.library.items)} icon={<Stack size={18} weight="duotone" />} tone="blue" />
            <DashboardMetric label={t("downloadedPosts")} value={number.format(snapshot.library.archivedItems)} detail={formatPercent(snapshot.library.archivedItems, snapshot.library.items)} icon={<VideoCamera size={18} weight="duotone" />} tone="amber" />
            <DashboardMetric label={t("mediaFiles")} value={number.format(snapshot.library.mediaFiles)} icon={<Database size={18} weight="duotone" />} tone="cyan" />
            <DashboardMetric label={t("creatorsCount")} value={number.format(snapshot.library.creators)} icon={<UsersThree size={18} weight="duotone" />} tone="green" />
            <DashboardMetric label={t("sourceCategories")} value={number.format(snapshot.library.sources)} detail={`${snapshot.library.completeSources} ${t("syncComplete")}`} icon={<Stack size={18} weight="duotone" />} tone="violet" />
          </div>
        </DashboardSection>

        <DashboardSection title={t("douyinAccountTitle")}>
          <div className="home-dashboard-grid is-five home-account-grid">
            <DashboardMetric label={t("nickname")} value={accountName} icon={<UserCircle size={18} weight="duotone" />} tone="blue" />
            <DashboardMetric label={t("douyinId")} value={accountId} icon={<IdentificationCard size={18} weight="duotone" />} tone="cyan" />
            <DashboardMetric label={t("accountStatus")} value={healthLabels[snapshot.account.status]} detail={snapshot.account.errorCode ?? t("liveConnectedStatus")} icon={<Heartbeat size={18} weight="duotone" />} tone={snapshot.account.status === "healthy" ? "green" : "amber"} />
            <DashboardMetric label={t("lastVerified")} value={timestamp(snapshot.account.lastVerifiedAt, locale)} icon={<CheckCircle size={18} weight="duotone" />} tone="green" />
            <DashboardMetric label={t("lastSync")} value={timestamp(snapshot.account.lastSyncAt, locale)} icon={<Pulse size={18} weight="duotone" />} tone="violet" />
          </div>
        </DashboardSection>

        <DashboardSection title={t("performanceTrendTitle")}>
          <div className="home-trend-grid">
            <DashboardTrend label={t("downloadSpeedTrend")} points={series} value={(point) => point.downloadSpeedBps} current={formatSpeed(snapshot.queue.speedBps)} tone="blue" emptyLabel={t("noMetricHistory")} />
            <DashboardTrend label={t("systemLoadTrend")} points={series} value={(point) => point.cpuLoadPercent} current={`${snapshot.system.cpuLoadPercent.toFixed(1)}%`} tone="violet" emptyLabel={t("noMetricHistory")} />
          </div>
        </DashboardSection>

        {snapshot.health.recentErrors > 0 ? <div className="home-alert" role="status"><WarningCircle size={18} weight="duotone" /><span>{snapshot.health.recentErrors} {t("recentErrors")}</span></div> : null}

        <SourceProgressSection sources={snapshot.sources} onOpenSource={onOpenSource} />
        <RuntimeSection runtime={snapshot.runtime} />
      </div>
    </main>
  );
}
