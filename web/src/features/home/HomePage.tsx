import {
  ArrowRight,
  CheckCircle,
  Cpu,
  Database,
  DownloadSimple,
  HardDrives,
  Heartbeat,
  Memory,
  Pulse,
  UserCircle,
  UsersThree,
  VideoCamera,
} from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";

import {
  updateSourceDownloadPolicy,
  type MetricPoint,
  type SourceProgress,
} from "../../app/api";
import { useI18n } from "../../i18n/context";
import { ThemeToggle } from "../../theme/ThemeToggle";
import { formatBytes, formatSpeed } from "../status/downloadFormat";
import { useDashboardStream } from "./useDashboardStream";

const numberFormat = new Intl.NumberFormat("zh-CN");
const sourceProgressTones = ["blue", "cyan", "green", "amber", "violet", "rose"] as const;

function formatTimestamp(value: number | null): string {
  if (value === null) return "—";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value * 1000));
}

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3600);
  return days > 0 ? `${days}天 ${hours}小时` : `${Math.max(hours, 0)}小时`;
}

function percentage(value: number, total: number): string {
  return `${total > 0 ? Math.round((value / total) * 100) : 0}%`;
}

function linePoints(values: number[], width = 600, height = 164): string {
  if (values.length === 0) return "";
  const maximum = Math.max(...values, 1);
  return values
    .map((value, index) => {
      const x = values.length === 1 ? width : (index / (values.length - 1)) * width;
      const y = height - (value / maximum) * (height - 20) - 10;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function TrendChart({
  label,
  points,
  value,
  formatValue,
  tone,
}: {
  label: string;
  points: MetricPoint[];
  value: (point: MetricPoint) => number;
  formatValue: (value: number) => string;
  tone: "blue" | "violet";
}) {
  const values = points.map(value);
  const latest = values.at(-1) ?? 0;
  return (
    <section className="home-chart-panel" data-chart-tone={tone}>
      <div className="home-section-title">
        <div>
          <span>{label}</span>
          <strong>{formatValue(latest)}</strong>
        </div>
        <span className="app-icon-well home-section-icon" data-icon-tone={tone}><Pulse size={20} weight="duotone" /></span>
      </div>
      {values.length === 0 ? (
        <p className="home-chart-empty">—</p>
      ) : (
        <svg role="img" aria-label={label} className="home-line-chart" viewBox="0 0 600 164" preserveAspectRatio="none">
          <path className="home-chart-gridline" d="M0 41H600M0 82H600M0 123H600" />
          <polyline points={linePoints(values)} fill="none" />
        </svg>
      )}
    </section>
  );
}

function HealthState({ status }: { status: string }) {
  const { t } = useI18n();
  const labels = {
    healthy: t("healthHealthy"),
    degraded: t("healthDegraded"),
    expired: t("healthExpired"),
    checking: t("healthChecking"),
    unknown: t("healthUnknown"),
  };
  return (
    <span className={`home-health-state is-${status}`}>
      <i />
      {labels[status as keyof typeof labels] ?? labels.unknown}
    </span>
  );
}

function SourceProgressTable({
  sources,
  onOpenSource,
}: {
  sources: SourceProgress[];
  onOpenSource: (sourceId: string) => void;
}) {
  const { t } = useI18n();
  const [localSources, setLocalSources] = useState(sources);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setLocalSources(sources), [sources]);

  async function toggle(source: SourceProgress) {
    const enabled = !source.autoDownloadEnabled;
    setPending(source.id);
    setError(null);
    setLocalSources((current) =>
      current.map((item) =>
        item.id === source.id ? { ...item, autoDownloadEnabled: enabled } : item,
      ),
    );
    try {
      const updated = await updateSourceDownloadPolicy(source.id, enabled);
      setLocalSources((current) =>
        current.map((item) => (item.id === source.id ? { ...item, ...updated } : item)),
      );
    } catch {
      setLocalSources((current) =>
        current.map((item) =>
          item.id === source.id ? { ...item, autoDownloadEnabled: source.autoDownloadEnabled } : item,
        ),
      );
      setError(source.id);
    } finally {
      setPending(null);
    }
  }

  return (
    <section className="home-source-section" role="region" aria-label={t("sourceDownloadProgress")}>
      <header className="home-source-heading">
        <div>
          <h2>{t("sourceDownloadProgress")}</h2>
          <p>{t("sourceDownloadDescription")}</p>
        </div>
      </header>
      <div className="home-source-list">
        {localSources.map((source, index) => {
          const tone = sourceProgressTones[index % sourceProgressTones.length];
          return (
          <article key={source.id} className="home-source-row" data-icon-tone={tone}>
            <button className="home-source-identity" type="button" onClick={() => onOpenSource(source.id)}>
              <span className="app-icon-well" data-icon-tone={tone}><Database size={18} weight="duotone" /></span>
              <div>
                <strong>{source.name}</strong>
                <small>{numberFormat.format(source.archived)} / {numberFormat.format(source.discovered)} {t("archivedWorks")}</small>
              </div>
            </button>
            <div className="home-source-progress">
              <div style={{ transform: `scaleX(${Math.min(Math.max(source.coveragePercent, 0), 100) / 100})` }} />
            </div>
            <dl className="home-source-metrics">
              <div><dt>{t("sourceSize")}</dt><dd>{formatBytes(source.archivedBytes)}</dd></div>
              <div><dt>{t("statusPending")}</dt><dd>{source.pending + source.running + source.retry}</dd></div>
              <div><dt>{t("archivedWorks")}</dt><dd>{source.coveragePercent.toFixed(1)}%</dd></div>
            </dl>
            <label className="home-policy-toggle">
              <input
                type="checkbox"
                role="switch"
                aria-label={`${t("automaticDownload")} ${source.name}`}
                checked={source.autoDownloadEnabled}
                disabled={pending === source.id}
                onChange={() => void toggle(source)}
              />
              <span />
            </label>
            <button className="home-source-open" type="button" aria-label={`${t("openSource")} ${source.name}`} onClick={() => onOpenSource(source.id)}>
              <ArrowRight size={18} />
            </button>
            {error === source.id ? <p className="home-source-error">{t("policyUpdateFailed")}</p> : null}
          </article>
          );
        })}
      </div>
    </section>
  );
}

export function HomePage({
  onOpenDownloads,
  onOpenSource,
}: {
  onOpenDownloads: () => void;
  onOpenSource: (sourceId: string) => void;
}) {
  const { t } = useI18n();
  const { snapshot, series, connected, loading, error } = useDashboardStream();
  const memoryPercent = useMemo(
    () => snapshot ? percentage(snapshot.system.memoryUsedBytes, snapshot.system.memoryTotalBytes) : "0%",
    [snapshot],
  );

  if (loading && !snapshot) return <div className="home-state home-skeleton" aria-label={t("loadingStatus")} />;
  if (error && !snapshot) return <div className="home-state"><p>{t("dashboardLoadFailed")}</p></div>;
  if (!snapshot) return null;

  const accountName = snapshot.account.account?.nickname ?? t("brand");
  return (
    <main className="home-page" aria-label={t("home")}>
      <header className="home-header">
        <div className="home-account">
          {snapshot.account.account?.avatarUrl ? <img src={snapshot.account.account.avatarUrl} alt="" /> : <span><UserCircle size={26} weight="duotone" /></span>}
          <div>
            <h1>{accountName}</h1>
            <p>{t("homeGreeting")}</p>
          </div>
        </div>
        <div className={`home-live-state${connected ? " is-live" : ""}`}><i />{t(connected ? "liveConnectedStatus" : "liveDisconnectedStatus")}</div>
        <ThemeToggle />
      </header>

      <div className="home-scroll">
        <section className="home-hero-grid" aria-label={t("dashboardOverview")}>
          <article className="home-storage-panel">
            <div className="home-section-title">
              <div><span>{t("archiveStorage")}</span><strong>{formatBytes(snapshot.storage.archiveBytes)}</strong></div>
              <span className="app-icon-well home-section-icon" data-icon-tone="cyan"><HardDrives size={22} weight="duotone" /></span>
            </div>
            <div className="home-storage-visual">
              <div className="home-storage-ring" style={{ "--storage-progress": `${snapshot.storage.usedPercent * 3.6}deg` } as React.CSSProperties}>
                <div><strong>{snapshot.storage.usedPercent}%</strong><small>{t("nasStorage")}</small></div>
              </div>
              <dl>
                <div><dt>{t("nasStorage")}</dt><dd>{formatBytes(snapshot.storage.totalBytes)}</dd></div>
                <div><dt>{t("freeStorage")}</dt><dd>{formatBytes(snapshot.storage.freeBytes)}</dd></div>
                <div><dt>{t("archiveStorage")}</dt><dd>{formatBytes(snapshot.storage.archiveBytes)}</dd></div>
              </dl>
            </div>
          </article>

          <article className="home-health-panel">
            <div className="home-section-title">
              <div><span>{t("douyinHealthTitle")}</span><strong>{accountName}</strong></div>
              <span className="app-icon-well home-section-icon" data-icon-tone="rose"><Heartbeat size={22} weight="duotone" /></span>
            </div>
            <HealthState status={snapshot.account.status} />
            <dl className="home-health-details">
              <div><dt>{t("lastVerified")}</dt><dd>{formatTimestamp(snapshot.account.lastVerifiedAt)}</dd></div>
              <div><dt>{t("lastSync")}</dt><dd>{formatTimestamp(snapshot.account.lastSyncAt)}</dd></div>
            </dl>
          </article>
        </section>

        <section className="home-metric-strip">
          <article><span className="app-icon-well home-metric-icon" data-icon-tone="blue"><VideoCamera size={19} weight="duotone" /></span><span>{t("downloadedPosts")}</span><strong>{numberFormat.format(snapshot.library.archivedItems)}</strong><small>/ {numberFormat.format(snapshot.library.items)}</small></article>
          <article><span className="app-icon-well home-metric-icon" data-icon-tone="cyan"><Database size={19} weight="duotone" /></span><span>{t("mediaFiles")}</span><strong>{numberFormat.format(snapshot.library.mediaFiles)}</strong></article>
          <article><span className="app-icon-well home-metric-icon" data-icon-tone="violet"><UsersThree size={19} weight="duotone" /></span><span>{t("creatorsCount")}</span><strong>{numberFormat.format(snapshot.library.creators)}</strong></article>
          <button type="button" onClick={onOpenDownloads}><span className="app-icon-well home-metric-icon" data-icon-tone="green"><DownloadSimple size={19} weight="duotone" /></span><span>{t("currentSpeed")}</span><strong>{formatSpeed(snapshot.queue.speedBps)}</strong><ArrowRight size={16} /></button>
        </section>

        <section className="home-chart-grid">
          <TrendChart label={t("downloadSpeedTrend")} points={series} value={(point) => point.downloadSpeedBps} formatValue={formatSpeed} tone="blue" />
          <TrendChart label={t("systemLoadTrend")} points={series} value={(point) => point.cpuLoadPercent} formatValue={(value) => `${value.toFixed(1)}%`} tone="violet" />
        </section>

        <section className="home-system-strip">
          <article><span className="app-icon-well home-system-icon" data-icon-tone="amber"><Memory size={19} weight="duotone" /></span><div><span>{t("memoryUsage")}</span><strong>{memoryPercent}</strong><small>{formatBytes(snapshot.system.memoryUsedBytes)} / {formatBytes(snapshot.system.memoryTotalBytes)}</small></div></article>
          <article><span className="app-icon-well home-system-icon" data-icon-tone="violet"><Cpu size={19} weight="duotone" /></span><div><span>{t("cpuUsage")}</span><strong>{snapshot.system.cpuLoadPercent.toFixed(1)}%</strong><small>{snapshot.system.cpuCount} CPU</small></div></article>
          <article><span className="app-icon-well home-system-icon" data-icon-tone="green"><CheckCircle size={19} weight="duotone" /></span><div><span>{t("serviceUptime")}</span><strong>{formatUptime(snapshot.health.uptimeSeconds)}</strong><small>{snapshot.health.recentErrors} {t("recentErrors")}</small></div></article>
        </section>

        <SourceProgressTable sources={snapshot.sources} onOpenSource={onOpenSource} />
      </div>
    </main>
  );
}
