import { ArrowClockwise, CheckCircle, CircleNotch, Database, HardDrives, Pulse, X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import {
  controlArchiveBatch,
  fetchArchiveBatches,
  fetchDashboard,
  fetchJobs,
  fetchStatus,
  fetchSyncRuns,
  triggerSync,
  type ArchiveBatch,
  type BootstrapStatus,
  type DashboardSnapshot,
  type DownloadSnapshot,
  type SyncRun,
} from "../../app/api";
import { useI18n } from "../../i18n/context";
import type { UtilityPanel } from "../navigation/CollectionRail";
import { DownloadMonitor } from "./DownloadMonitor";
import { formatBytes, formatSpeed } from "./downloadFormat";

const EMPTY_DOWNLOAD_SNAPSHOT: DownloadSnapshot = {
  summary: { pending: 0, running: 0, retry: 0, failed: 0, completed: 0, downloadedBytes: 0, totalBytes: 0, speedBps: 0, etaSeconds: 0 },
  items: [],
};

export function ArchiveStatusPanel({ kind, onClose }: { kind: UtilityPanel; onClose: () => void }) {
  const { locale, setLocale, t } = useI18n();
  const [downloads, setDownloads] = useState<DownloadSnapshot>(EMPTY_DOWNLOAD_SNAPSHOT);
  const [runs, setRuns] = useState<SyncRun[]>([]);
  const [status, setStatus] = useState<BootstrapStatus | null>(null);
  const [dashboard, setDashboard] = useState<DashboardSnapshot | null>(null);
  const [batches, setBatches] = useState<ArchiveBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [queuedRun, setQueuedRun] = useState<number | null>(null);
  const [activityTab, setActivityTab] = useState<"downloads" | "sync">("downloads");

  useEffect(() => {
    let cancelled = false;
    let refreshing = false;
    async function load(showLoading: boolean) {
      if (refreshing) return;
      refreshing = true;
      if (showLoading) setLoading(true);
      setError(false);
      try {
        if (kind === "dashboard") {
          const [dashboardResult, batchResult] = await Promise.all([fetchDashboard(), fetchArchiveBatches()]);
          if (!cancelled) {
            setDashboard(dashboardResult);
            setBatches(batchResult.items);
          }
        } else if (kind === "activity") {
          const [jobResult, runResult] = await Promise.all([fetchJobs(), fetchSyncRuns()]);
          if (!cancelled) {
            setDownloads(jobResult);
            setRuns(runResult.items);
          }
        } else if (kind === "downloads") {
          const result = await fetchJobs();
          if (!cancelled) setDownloads(result);
        } else if (kind === "sync") {
          const result = await fetchSyncRuns();
          if (!cancelled) setRuns(result.items);
        } else {
          const result = await fetchStatus();
          if (!cancelled) setStatus(result);
        }
      } catch {
        if (!cancelled) setError(true);
      } finally {
        refreshing = false;
        if (!cancelled && showLoading) setLoading(false);
      }
    }
    void load(true);
    const refreshMilliseconds = kind === "settings" ? undefined : kind === "sync" ? 5_000 : 1_000;
    const interval = refreshMilliseconds === undefined ? undefined : window.setInterval(() => void load(false), refreshMilliseconds);
    return () => {
      cancelled = true;
      if (interval !== undefined) window.clearInterval(interval);
    };
  }, [kind]);

  async function controlBatch(batchId: number, action: "pause" | "resume" | "cancel") {
    setError(false);
    try {
      const updated = await controlArchiveBatch(batchId, action);
      setBatches((current) => current.map((batch) => batch.id === batchId ? { ...batch, ...updated } : batch));
    } catch {
      setError(true);
    }
  }

  async function runFullSync() {
    setSyncing(true);
    setError(false);
    try {
      const result = await triggerSync(true);
      setQueuedRun(result.runId);
      setRuns((await fetchSyncRuns()).items);
    } catch {
      setError(true);
    } finally {
      setSyncing(false);
    }
  }

  const title = kind === "dashboard" ? t("dashboard") : kind === "downloads" ? t("downloadJobs") : kind === "sync" ? t("syncStatus") : kind === "activity" ? t("mobileActivity") : t("settings");

  return (
    <div className="utility-overlay" onClick={onClose}>
      <aside role="dialog" aria-modal="true" className={`cinematic-drawer utility-drawer${kind === "dashboard" ? " utility-dashboard-drawer" : ""}`} onClick={(event) => event.stopPropagation()} aria-label={title}>
        <header className="utility-drawer-header">
          <h2>{title}</h2>
          <button type="button" onClick={onClose} aria-label={t("closePanel")} className="utility-close-button"><X size={20} /></button>
        </header>
        <div className="utility-drawer-body">
          {loading ? <p className="utility-loading"><CircleNotch className="animate-spin" size={18} />{t("loadingStatus")}</p> : null}
          {error ? <p className="utility-error">{t("statusLoadFailed")}</p> : null}
          {!loading && dashboard && kind === "dashboard" ? <DashboardOverview snapshot={dashboard} batches={batches} onControl={controlBatch} /> : null}
          {!loading && kind === "downloads" ? <DownloadMonitor snapshot={downloads} /> : null}
          {!loading && kind === "activity" ? (
            <div>
              <div role="tablist" aria-label={t("activityTabs")} className="utility-tabs">
                <button role="tab" aria-selected={activityTab === "downloads"} type="button" onClick={() => setActivityTab("downloads")} className={`touch-target${activityTab === "downloads" ? " is-active" : ""}`}>{t("activityDownloads")}</button>
                <button role="tab" aria-selected={activityTab === "sync"} type="button" onClick={() => setActivityTab("sync")} className={`touch-target${activityTab === "sync" ? " is-active" : ""}`}>{t("activitySync")}</button>
              </div>
              {activityTab === "downloads" ? <DownloadMonitor snapshot={downloads} /> : <SyncPanel runs={runs} syncing={syncing} queuedRun={queuedRun} onSync={runFullSync} />}
            </div>
          ) : null}
          {!loading && !error && kind === "sync" ? (
            <SyncPanel runs={runs} syncing={syncing} queuedRun={queuedRun} onSync={runFullSync} />
          ) : null}
          {!loading && !error && kind === "settings" ? (
            <div className="settings-grid">
              <StatusCard icon={<CheckCircle size={22} />} title={status?.douyinAuthenticated ? t("douyinConnected") : t("douyinDisconnected")} body={t("sessionPreserved")} />
              <StatusCard icon={<Database size={22} />} title={t("permanentRetention")} body={t("permanentRetentionBody")} />
              <div className="status-card language-card">
                <p>{t("language")}</p>
                <div className="language-options">
                  <button type="button" onClick={() => setLocale("zh-CN")} className={locale === "zh-CN" ? "is-active" : ""}>{t("chinese")}</button>
                  <button type="button" onClick={() => setLocale("en")} className={locale === "en" ? "is-active" : ""}>{t("english")}</button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function DashboardOverview({ snapshot, batches, onControl }: { snapshot: DashboardSnapshot; batches: ArchiveBatch[]; onControl: (batchId: number, action: "pause" | "resume" | "cancel") => Promise<void> }) {
  const { locale, t } = useI18n();
  const number = new Intl.NumberFormat(locale);
  const memoryPercent = snapshot.system.memoryTotalBytes > 0
    ? Math.round(snapshot.system.memoryUsedBytes / snapshot.system.memoryTotalBytes * 100)
    : 0;
  return (
    <section aria-label={t("dashboardOverview")} className="dashboard-overview">
      <div className="dashboard-metric-grid">
        <MetricCard icon={<HardDrives size={20} />} label={t("storageUsage")} value={`${snapshot.storage.usedPercent}%`} detail={`${formatBytes(snapshot.storage.usedBytes)} / ${formatBytes(snapshot.storage.totalBytes)}`} progress={snapshot.storage.usedPercent} />
        <MetricCard icon={<Pulse size={20} />} label={t("downloadSpeed")} value={formatSpeed(snapshot.queue.speedBps)} detail={`${snapshot.queue.running} ${t("statusRunning")} · ${snapshot.queue.pending} ${t("statusPending")}`} />
        <MetricCard icon={<Pulse size={20} />} label={t("systemLoad")} value={`${snapshot.system.cpuLoadPercent}%`} detail={`${snapshot.system.cpuCount} CPU · load ${snapshot.system.loadAverage1m}`} progress={snapshot.system.cpuLoadPercent} />
        <MetricCard icon={<Database size={20} />} label={t("processMemory")} value={formatBytes(snapshot.system.processMemoryBytes)} detail={`${memoryPercent}% · ${formatBytes(snapshot.system.memoryUsedBytes)} / ${formatBytes(snapshot.system.memoryTotalBytes)}`} progress={memoryPercent} />
        <MetricCard icon={<Database size={20} />} label={t("libraryIntegrity")} value={`${number.format(snapshot.library.archivedItems)} / ${number.format(snapshot.library.items)}`} detail={`${snapshot.library.completeSources}/${snapshot.library.sources} ${t("syncStatus")}`} progress={snapshot.library.items > 0 ? snapshot.library.archivedItems / snapshot.library.items * 100 : 0} />
        <MetricCard icon={<Pulse size={20} />} label={t("recentErrors")} value={number.format(snapshot.health.recentErrors)} detail={`${formatBytes(snapshot.library.archivedBytes)} · ${number.format(snapshot.library.creators)} creators`} />
      </div>
      <section className="dashboard-batches" aria-label={t("archiveBatches")}>
        <div className="dashboard-section-heading"><div><span>{t("archiveBatches")}</span><strong>{batches.length}</strong></div></div>
        {batches.length === 0 ? <p className="download-empty">{t("batchEmpty")}</p> : (
          <div className="dashboard-batch-list">
            {batches.map((batch) => {
              const completed = batch.completedCount ?? 0;
              const total = batch.discoveredCount ?? 0;
              return (
                <article key={batch.id} className="dashboard-batch-card">
                  <div className="dashboard-batch-main"><div><small>#{batch.id} · {batch.kind}</small><strong>{batch.targetId}</strong></div><span className={`download-status download-status-${batch.status}`}>{batch.status}</span></div>
                  <div className="dashboard-batch-progress"><progress aria-label={`${batch.targetId} ${t("queueProgress")}`} max={Math.max(total, 1)} value={completed} /><span>{completed} / {total}</span></div>
                  {batch.errorCode ? <p className="download-failure">{batch.errorCode}</p> : null}
                  {!["completed", "failed", "cancelled"].includes(batch.status) ? (
                    <div className="dashboard-batch-actions">
                      {batch.status === "paused"
                        ? <button type="button" onClick={() => void onControl(batch.id, "resume")}>{t("resumeBatch")}</button>
                        : <button type="button" onClick={() => void onControl(batch.id, "pause")}>{t("pauseBatch")}</button>}
                      <button type="button" onClick={() => void onControl(batch.id, "cancel")}>{t("cancelBatch")}</button>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        )}
      </section>
    </section>
  );
}

function MetricCard({ icon, label, value, detail, progress }: { icon: React.ReactNode; label: string; value: string; detail: string; progress?: number }) {
  return (
    <article className="dashboard-metric-card">
      <div className="dashboard-metric-label"><span>{icon}</span><p>{label}</p></div>
      <strong>{value}</strong>
      <small>{detail}</small>
      {progress !== undefined ? <progress aria-label={label} max={100} value={Math.min(Math.max(progress, 0), 100)} /> : null}
    </article>
  );
}

function SyncList({ runs }: { runs: SyncRun[] }) {
  const { t } = useI18n();
  if (!runs.length) return <p className="sync-empty">{t("syncEmpty")}</p>;
  return <div className="sync-list">{runs.map((run) => <article key={run.id} className="sync-run"><div><p>#{run.id} · {run.mode}</p><span>{run.status}</span></div><small>{t("discoveredLabel")} {run.discovered} · {t("enqueuedLabel")} {run.enqueued}</small>{run.errorCode ? <em>{run.errorCode}</em> : null}</article>)}</div>;
}

function SyncPanel({ runs, syncing, queuedRun, onSync }: { runs: SyncRun[]; syncing: boolean; queuedRun: number | null; onSync: () => Promise<void> }) {
  const { t } = useI18n();
  return <div><button type="button" disabled={syncing} onClick={() => void onSync()} className="friendly-button friendly-button-primary friendly-button-full"><ArrowClockwise className={syncing ? "animate-spin" : ""} size={18} />{t("fullSyncNow")}</button>{queuedRun ? <p className="sync-queued">{t("fullSyncQueued").replace("{id}", String(queuedRun))}</p> : null}<SyncList runs={runs} /></div>;
}

function StatusCard({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return <article className="status-card"><div>{icon}<h3>{title}</h3></div><p>{body}</p></article>;
}
