import { ArrowClockwise, CheckCircle, CircleNotch, Database, X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import {
  fetchJobs,
  fetchStatus,
  fetchSyncRuns,
  triggerSync,
  type BootstrapStatus,
  type DownloadJob,
  type SyncRun,
} from "../../app/api";
import { useI18n } from "../../i18n/context";
import type { UtilityPanel } from "../navigation/CollectionRail";

export function ArchiveStatusPanel({ kind, onClose }: { kind: UtilityPanel; onClose: () => void }) {
  const { locale, setLocale, t } = useI18n();
  const [jobs, setJobs] = useState<DownloadJob[]>([]);
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
            setJobs(jobResult.items);
            setRuns(runResult.items);
          }
        } else if (kind === "downloads") {
          const result = await fetchJobs();
          if (!cancelled) setJobs(result.items);
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
    const interval = kind === "settings" ? undefined : window.setInterval(() => void load(false), 5_000);
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
    <div className="fixed inset-0 z-10 bg-black/55 backdrop-blur-sm" onClick={onClose}>
      <aside role="dialog" aria-modal="true" className="absolute inset-y-0 right-0 flex w-[min(92vw,430px)] flex-col border-l border-white/10 bg-[#12151a] shadow-2xl max-lg:inset-x-0 max-lg:bottom-0 max-lg:top-auto max-lg:max-h-[88dvh] max-lg:w-full max-lg:rounded-t-[28px] max-lg:border-l-0 max-lg:border-t" onClick={(event) => event.stopPropagation()} aria-label={title}>
        <header className="flex h-[76px] shrink-0 items-center justify-between border-b border-white/8 px-6">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label={t("closePanel")} className="grid h-11 w-11 place-items-center rounded-full hover:bg-white/[.06]"><X size={20} /></button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6">
          {loading ? <p className="flex items-center gap-2 text-sm text-[#8f959f]"><CircleNotch className="animate-spin" size={18} />{t("loadingStatus")}</p> : null}
          {error ? <p className="rounded-xl border border-[#f16761]/25 bg-[#f16761]/10 p-4 text-sm text-[#f5aaa6]">{t("statusLoadFailed")}</p> : null}
          {!loading && !error && kind === "downloads" ? <DownloadList jobs={jobs} /> : null}
          {!loading && !error && kind === "activity" ? (
            <div>
              <div role="tablist" aria-label={t("activityTabs")} className="mb-5 grid grid-cols-2 rounded-xl bg-white/[.05] p-1">
                <button role="tab" aria-selected={activityTab === "downloads"} type="button" onClick={() => setActivityTab("downloads")} className={`touch-target min-h-11 rounded-lg text-sm font-medium ${activityTab === "downloads" ? "bg-white text-[#101318]" : "text-[#aeb3bc]"}`}>{t("activityDownloads")}</button>
                <button role="tab" aria-selected={activityTab === "sync"} type="button" onClick={() => setActivityTab("sync")} className={`touch-target min-h-11 rounded-lg text-sm font-medium ${activityTab === "sync" ? "bg-white text-[#101318]" : "text-[#aeb3bc]"}`}>{t("activitySync")}</button>
              </div>
              {activityTab === "downloads" ? <DownloadList jobs={jobs} /> : <SyncPanel runs={runs} syncing={syncing} queuedRun={queuedRun} onSync={runFullSync} />}
            </div>
          ) : null}
          {!loading && !error && kind === "sync" ? (
            <SyncPanel runs={runs} syncing={syncing} queuedRun={queuedRun} onSync={runFullSync} />
          ) : null}
          {!loading && !error && kind === "settings" ? (
            <div className="grid gap-4">
              <StatusCard icon={<CheckCircle size={22} />} title={status?.douyinAuthenticated ? t("douyinConnected") : t("douyinDisconnected")} body={t("sessionPreserved")} />
              <StatusCard icon={<Database size={22} />} title={t("permanentRetention")} body={t("permanentRetentionBody")} />
              <div className="rounded-2xl border border-white/8 bg-white/[.03] p-5">
                <p className="text-sm font-medium">{t("language")}</p>
                <div className="mt-4 grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => setLocale("zh-CN")} className={`min-h-10 rounded-lg text-sm ${locale === "zh-CN" ? "bg-white text-black" : "bg-white/[.06]"}`}>{t("chinese")}</button>
                  <button type="button" onClick={() => setLocale("en")} className={`min-h-10 rounded-lg text-sm ${locale === "en" ? "bg-white text-black" : "bg-white/[.06]"}`}>{t("english")}</button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function DownloadList({ jobs }: { jobs: DownloadJob[] }) {
  const { t } = useI18n();
  if (!jobs.length) return <p className="text-sm text-[#8f959f]">{t("jobsEmpty")}</p>;
  return <div className="grid gap-3">{jobs.map((job) => <article key={job.id} className="rounded-xl border border-white/8 bg-white/[.03] p-4"><div className="flex items-center justify-between gap-3"><p className="truncate text-sm font-medium">{t("itemLabel")} {job.remoteId}</p><span className="rounded-full bg-white/[.06] px-2.5 py-1 text-xs text-[#b9bec6]">{job.status}</span></div><p className="mt-2 text-xs text-[#737984]">{t("attemptsLabel")} {job.attempts}{job.errorCode ? ` · ${job.errorCode}` : ""}</p></article>)}</div>;
}

function SyncList({ runs }: { runs: SyncRun[] }) {
  const { t } = useI18n();
  if (!runs.length) return <p className="mt-5 text-sm text-[#8f959f]">{t("syncEmpty")}</p>;
  return <div className="mt-5 grid gap-3">{runs.map((run) => <article key={run.id} className="rounded-xl border border-white/8 bg-white/[.03] p-4"><div className="flex items-center justify-between"><p className="text-sm font-medium">#{run.id} · {run.mode}</p><span className="text-xs text-[#b9bec6]">{run.status}</span></div><p className="mt-2 text-xs text-[#737984]">{t("discoveredLabel")} {run.discovered} · {t("enqueuedLabel")} {run.enqueued}</p>{run.errorCode ? <p className="mt-2 text-xs text-[#f5aaa6]">{run.errorCode}</p> : null}</article>)}</div>;
}

function SyncPanel({ runs, syncing, queuedRun, onSync }: { runs: SyncRun[]; syncing: boolean; queuedRun: number | null; onSync: () => Promise<void> }) {
  const { t } = useI18n();
  return <div><button type="button" disabled={syncing} onClick={() => void onSync()} className="flex min-h-11 w-full items-center justify-center gap-2 rounded-xl bg-[#f16761] px-4 text-sm font-semibold text-white active:scale-[.98] disabled:opacity-60"><ArrowClockwise className={syncing ? "animate-spin" : ""} size={18} />{t("fullSyncNow")}</button>{queuedRun ? <p className="mt-3 text-sm text-[#9da3ad]">{t("fullSyncQueued").replace("{id}", String(queuedRun))}</p> : null}<SyncList runs={runs} /></div>;
}

function StatusCard({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return <article className="rounded-2xl border border-white/8 bg-white/[.03] p-5"><div className="flex items-center gap-3 text-[#f16761]">{icon}<h3 className="text-sm font-semibold text-white">{title}</h3></div><p className="mt-3 text-sm leading-6 text-[#8f959f]">{body}</p></article>;
}
