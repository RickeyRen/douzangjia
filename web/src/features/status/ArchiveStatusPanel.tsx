import { ArrowClockwise, CheckCircle, CircleNotch, Database, X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import {
  fetchJobs,
  fetchStatus,
  fetchSyncRuns,
  triggerSync,
  type BootstrapStatus,
  type DownloadSnapshot,
  type SyncRun,
} from "../../app/api";
import { useI18n } from "../../i18n/context";
import type { UtilityPanel } from "../navigation/CollectionRail";
import { DownloadMonitor } from "./DownloadMonitor";

const EMPTY_DOWNLOAD_SNAPSHOT: DownloadSnapshot = {
  summary: { pending: 0, running: 0, retry: 0, failed: 0, completed: 0, downloadedBytes: 0, totalBytes: 0, speedBps: 0, etaSeconds: 0 },
  items: [],
};

export function ArchiveStatusPanel({ kind, onClose }: { kind: UtilityPanel; onClose: () => void }) {
  const { locale, setLocale, t } = useI18n();
  const [downloads, setDownloads] = useState<DownloadSnapshot>(EMPTY_DOWNLOAD_SNAPSHOT);
  const [runs, setRuns] = useState<SyncRun[]>([]);
  const [status, setStatus] = useState<BootstrapStatus | null>(null);
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
        if (kind === "activity") {
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

  const title = kind === "downloads" ? t("downloadJobs") : kind === "sync" ? t("syncStatus") : kind === "activity" ? t("mobileActivity") : t("settings");

  return (
    <div className="utility-overlay" onClick={onClose}>
      <aside role="dialog" aria-modal="true" className="cinematic-drawer utility-drawer" onClick={(event) => event.stopPropagation()} aria-label={title}>
        <header className="utility-drawer-header">
          <h2>{title}</h2>
          <button type="button" onClick={onClose} aria-label={t("closePanel")} className="utility-close-button"><X size={20} /></button>
        </header>
        <div className="utility-drawer-body">
          {loading ? <p className="utility-loading"><CircleNotch className="animate-spin" size={18} />{t("loadingStatus")}</p> : null}
          {error ? <p className="utility-error">{t("statusLoadFailed")}</p> : null}
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
