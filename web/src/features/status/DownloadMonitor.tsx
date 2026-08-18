import { CaretDown, CaretUp, DownloadSimple, Files, Gauge, Timer } from "@phosphor-icons/react";
import { memo, useEffect, useState } from "react";

import type { DownloadAsset, DownloadJob, DownloadSnapshot } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { formatBytes, formatDateTime, formatEta, formatSpeed } from "./downloadFormat";

const STATUS_KEYS = {
  pending: "statusPending",
  running: "statusRunning",
  retry: "statusRetry",
  failed: "statusFailed",
  completed: "statusCompleted",
  ready: "statusReady",
} as const;

const ERROR_KEYS = {
  MEDIA_HTTP_ERROR: "errorMediaHttp",
  MEDIA_GONE: "errorMediaGone",
  RATE_LIMITED: "errorRateLimited",
  DOWNLOAD_FAILED: "errorDownloadFailed",
  FILESYSTEM_ERROR: "errorFilesystem",
  STORAGE_FULL: "errorStorageFull",
  WORKER_RESTARTED: "errorWorkerRestarted",
} as const;

type Translator = ReturnType<typeof useI18n>["t"];

function statusText(status: string, t: Translator): string {
  const key = STATUS_KEYS[status as keyof typeof STATUS_KEYS];
  return key ? t(key) : status;
}

function errorText(errorCode: string | null, t: Translator): string | null {
  if (!errorCode) return null;
  const key = ERROR_KEYS[errorCode as keyof typeof ERROR_KEYS];
  return key ? `${t(key)} · ${errorCode}` : errorCode;
}

function ProgressBar({
  downloaded,
  total,
  label,
}: {
  downloaded: number;
  total: number | null;
  label: string;
}) {
  if (total === null || total <= 0) {
    return <div role="progressbar" aria-label={label} className="download-progress-indeterminate h-2 overflow-hidden rounded-full bg-white/10" />;
  }
  return <progress aria-label={label} className="download-progress h-2 w-full" max={total} value={Math.min(downloaded, total)} />;
}

function ByteProgress({ downloaded, total }: { downloaded: number; total: number | null }) {
  const { t } = useI18n();
  return <span>{total === null ? `${formatBytes(downloaded)} · ${t("totalUnknown")}` : `${formatBytes(downloaded)} / ${formatBytes(total)}`}</span>;
}

function QueueSummary({ snapshot }: { snapshot: DownloadSnapshot }) {
  const { locale, t } = useI18n();
  const { summary } = snapshot;
  const counts = [
    ["running", t("statusRunning"), summary.running],
    ["pending", t("statusPending"), summary.pending],
    ["retry", t("statusRetry"), summary.retry],
    ["failed", t("statusFailed"), summary.failed],
    ["completed", t("statusCompleted"), summary.completed],
  ] as const;
  return (
    <section className="rounded-2xl border border-white/10 bg-gradient-to-br from-[#20242b] to-[#171a20] p-5 shadow-xl" aria-label={t("downloadQueue")}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[.18em] text-[#8f959f]">{t("queueProgress")}</p>
          <p className="mt-2 text-lg font-semibold"><ByteProgress downloaded={summary.downloadedBytes} total={summary.totalBytes} /></p>
        </div>
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[#f16761]/15 text-[#f58f89]"><DownloadSimple size={22} /></span>
      </div>
      <div className="mt-4"><ProgressBar downloaded={summary.downloadedBytes} total={summary.totalBytes} label={t("queueDownloadProgress")} /></div>
      <div className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
        <div className="rounded-xl bg-black/20 p-3"><p className="flex items-center gap-1.5 text-[#8f959f]"><Gauge size={15} />{t("downloadSpeed")}</p><p className="mt-1 font-semibold text-white">{formatSpeed(summary.speedBps)}</p></div>
        <div className="rounded-xl bg-black/20 p-3"><p className="flex items-center gap-1.5 text-[#8f959f]"><Timer size={15} />{t("remainingTime")}</p><p className="mt-1 font-semibold text-white">{formatEta(summary.etaSeconds, locale)}</p></div>
        <div className="col-span-2 rounded-xl bg-black/20 p-3 sm:col-span-1"><p className="flex items-center gap-1.5 text-[#8f959f]"><Files size={15} />{t("downloadJobs")}</p><p className="mt-1 font-semibold text-white">{snapshot.items.length}</p></div>
      </div>
      <div className="mt-4 grid grid-cols-5 gap-1.5" aria-label={t("queueStates")}>
        {counts.map(([status, label, value]) => <div key={status} className="min-w-0 rounded-lg bg-white/[.04] px-1.5 py-2 text-center"><p className="truncate text-[10px] text-[#7f858f]">{label}</p><p className="mt-0.5 text-sm font-semibold">{value}</p></div>)}
      </div>
    </section>
  );
}

function AssetRow({ asset }: { asset: DownloadAsset }) {
  const { locale, t } = useI18n();
  return (
    <li className="rounded-xl border border-white/8 bg-black/20 p-3">
      <div className="flex items-center justify-between gap-3"><p className="truncate text-xs font-medium text-white">{asset.fileName}</p><span className="shrink-0 text-[11px] text-[#aeb3bc]">{statusText(asset.status, t)}</span></div>
      <div className="mt-2"><ProgressBar downloaded={asset.downloadedBytes} total={asset.totalBytes} label={`${asset.fileName} ${t("fileDownloadProgress")}`} /></div>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-[11px] text-[#7f858f]"><ByteProgress downloaded={asset.downloadedBytes} total={asset.totalBytes} /><span>{asset.mediaType} · {formatSpeed(asset.speedBps)} · {formatEta(asset.etaSeconds, locale)}</span></div>
    </li>
  );
}

function RetryCountdown({ nextAttemptAt }: { nextAttemptAt: number }) {
  const { t } = useI18n();
  const [nowSeconds, setNowSeconds] = useState(0);
  useEffect(() => {
    const update = () => setNowSeconds(Math.floor(Date.now() / 1000));
    update();
    const interval = window.setInterval(update, 1_000);
    return () => window.clearInterval(interval);
  }, []);
  const retrySeconds = Math.max(0, nextAttemptAt - nowSeconds);
  return <>{retrySeconds > 0 ? t("retryIn").replace("{seconds}", String(retrySeconds)) : t("retryReady")}</>;
}

const DownloadTaskCard = memo(function DownloadTaskCard({ job }: { job: DownloadJob }) {
  const { locale, t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const detailsId = `download-job-${job.id}`;
  const failure = errorText(job.errorCode, t);
  return (
    <article className="download-task-card overflow-hidden rounded-2xl border border-white/8 bg-white/[.035]">
      <button type="button" aria-expanded={expanded} aria-controls={detailsId} onClick={() => setExpanded((value) => !value)} className="touch-target w-full p-4 text-left active:bg-white/[.04]">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0"><p className="truncate text-sm font-semibold text-white">{job.description || `${t("itemLabel")} ${job.remoteId}`}</p><p className="mt-1 truncate text-xs text-[#737984]">{job.author || job.remoteId}</p></div>
          <span className={`download-status download-status-${job.status} shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium`}>{statusText(job.status, t)}</span>
        </div>
        <div className="mt-3"><ProgressBar downloaded={job.downloadedBytes} total={job.totalBytes} label={`${job.description || job.remoteId} ${t("taskDownloadProgress")}`} /></div>
        <div className="mt-2 flex items-center justify-between gap-3 text-xs text-[#8f959f]"><ByteProgress downloaded={job.downloadedBytes} total={job.totalBytes} /><span className="flex shrink-0 items-center gap-1">{formatSpeed(job.speedBps)} {expanded ? <CaretUp size={14} /> : <CaretDown size={14} />}</span></div>
        {job.status === "retry" ? <p className="mt-2 text-xs text-[#eaa09b]"><RetryCountdown nextAttemptAt={job.nextAttemptAt} /></p> : null}
      </button>
      {expanded ? (
        <div id={detailsId} className="border-t border-white/8 px-4 pb-4 pt-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-xs">
            <div><dt className="text-[#6f757f]">{t("downloadSpeed")}</dt><dd className="mt-1 text-[#d7d9dd]">{formatSpeed(job.speedBps)}</dd></div>
            <div><dt className="text-[#6f757f]">{t("remainingTime")}</dt><dd className="mt-1 text-[#d7d9dd]">{formatEta(job.etaSeconds, locale)}</dd></div>
            <div><dt className="text-[#6f757f]">{t("attemptsLabel")}</dt><dd className="mt-1 text-[#d7d9dd]">{job.attempts}</dd></div>
            <div><dt className="text-[#6f757f]">{t("updatedLabel")}</dt><dd className="mt-1 text-[#d7d9dd]">{formatDateTime(job.updatedAt, locale)}</dd></div>
          </dl>
          <div className="mt-3 text-xs"><p className="text-[#6f757f]">{t("source")}</p><p className="mt-1 text-[#d7d9dd]">{job.author || t("unknownAuthor")}</p></div>
          <div className="mt-3 text-xs"><p className="text-[#6f757f]">{t("collectionLabel")}</p><p className="mt-1 text-[#d7d9dd]">{job.collections.length ? job.collections.join(" · ") : "—"}</p></div>
          {failure ? <p className="mt-3 rounded-xl border border-[#f16761]/20 bg-[#f16761]/10 p-3 text-xs leading-5 text-[#f5aaa6]">{failure}</p> : null}
          <p className="mb-2 mt-4 text-xs font-medium text-[#8f959f]">{t("fileDetails")}</p>
          <ul className="grid gap-2">{job.assets.map((asset) => <AssetRow key={asset.index} asset={asset} />)}</ul>
        </div>
      ) : null}
    </article>
  );
});

export function DownloadMonitor({ snapshot }: { snapshot: DownloadSnapshot }) {
  const { t } = useI18n();
  return (
    <div className="grid gap-4">
      <QueueSummary snapshot={snapshot} />
      {snapshot.items.length ? <div className="grid gap-3">{snapshot.items.map((job) => <DownloadTaskCard key={job.id} job={job} />)}</div> : <p className="text-sm text-[#8f959f]">{t("jobsEmpty")}</p>}
    </div>
  );
}
