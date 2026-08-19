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
    return <div role="progressbar" aria-label={label} className="download-progress-indeterminate" />;
  }
  return <progress aria-label={label} className="download-progress" max={total} value={Math.min(downloaded, total)} />;
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
    <section className="download-queue-summary" aria-label={t("downloadQueue")}>
      <div className="download-summary-header">
        <div>
          <p>{t("queueProgress")}</p>
          <strong><ByteProgress downloaded={summary.downloadedBytes} total={summary.totalBytes} /></strong>
        </div>
        <span className="download-summary-icon"><DownloadSimple size={21} /></span>
      </div>
      <div className="download-summary-progress"><ProgressBar downloaded={summary.downloadedBytes} total={summary.totalBytes} label={t("queueDownloadProgress")} /></div>
      <div className="download-metrics">
        <div><p><Gauge size={15} />{t("downloadSpeed")}</p><strong>{formatSpeed(summary.speedBps)}</strong></div>
        <div><p><Timer size={15} />{t("remainingTime")}</p><strong>{formatEta(summary.etaSeconds, locale)}</strong></div>
        <div><p><Files size={15} />{t("downloadJobs")}</p><strong>{snapshot.items.length}</strong></div>
      </div>
      <div className="download-state-counts" aria-label={t("queueStates")}>
        {counts.map(([status, label, value]) => <div key={status}><p>{label}</p><strong>{value}</strong></div>)}
      </div>
    </section>
  );
}

function AssetRow({ asset }: { asset: DownloadAsset }) {
  const { locale, t } = useI18n();
  return (
    <li className="download-asset-row">
      <div className="download-asset-heading"><p>{asset.fileName}</p><span>{statusText(asset.status, t)}</span></div>
      <div className="download-asset-progress"><ProgressBar downloaded={asset.downloadedBytes} total={asset.totalBytes} label={`${asset.fileName} ${t("fileDownloadProgress")}`} /></div>
      <div className="download-asset-meta"><ByteProgress downloaded={asset.downloadedBytes} total={asset.totalBytes} /><span>{asset.mediaType} · {formatSpeed(asset.speedBps)} · {formatEta(asset.etaSeconds, locale)}</span></div>
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
    <article className="download-task-card">
      <button type="button" aria-expanded={expanded} aria-controls={detailsId} onClick={() => setExpanded((value) => !value)} className="touch-target download-task-toggle">
        <div className="download-task-heading">
          <div><p>{job.description || `${t("itemLabel")} ${job.remoteId}`}</p><small>{job.author || job.remoteId}</small></div>
          <span className={`download-status download-status-${job.status}`}>{statusText(job.status, t)}</span>
        </div>
        <div className="download-task-progress"><ProgressBar downloaded={job.downloadedBytes} total={job.totalBytes} label={`${job.description || job.remoteId} ${t("taskDownloadProgress")}`} /></div>
        <div className="download-task-meta"><ByteProgress downloaded={job.downloadedBytes} total={job.totalBytes} /><span>{formatSpeed(job.speedBps)} {expanded ? <CaretUp size={14} /> : <CaretDown size={14} />}</span></div>
        {job.status === "retry" ? <p className="download-retry"><RetryCountdown nextAttemptAt={job.nextAttemptAt} /></p> : null}
      </button>
      {expanded ? (
        <div id={detailsId} className="download-task-details">
          <dl className="download-detail-grid">
            <div><dt>{t("downloadSpeed")}</dt><dd>{formatSpeed(job.speedBps)}</dd></div>
            <div><dt>{t("remainingTime")}</dt><dd>{formatEta(job.etaSeconds, locale)}</dd></div>
            <div><dt>{t("attemptsLabel")}</dt><dd>{job.attempts}</dd></div>
            <div><dt>{t("updatedLabel")}</dt><dd>{formatDateTime(job.updatedAt, locale)}</dd></div>
          </dl>
          <div className="download-detail-line"><p>{t("source")}</p><span>{job.author || t("unknownAuthor")}</span></div>
          <div className="download-detail-line"><p>{t("collectionLabel")}</p><span>{job.collections.length ? job.collections.join(" · ") : "—"}</span></div>
          {failure ? <p className="download-failure">{failure}</p> : null}
          <p className="download-file-heading">{t("fileDetails")}</p>
          <ul className="download-assets">{job.assets.map((asset) => <AssetRow key={asset.index} asset={asset} />)}</ul>
        </div>
      ) : null}
    </article>
  );
});

export function DownloadMonitor({ snapshot }: { snapshot: DownloadSnapshot }) {
  const { t } = useI18n();
  return (
    <div className="download-monitor">
      <QueueSummary snapshot={snapshot} />
      {snapshot.items.length ? <div className="download-task-list">{snapshot.items.map((job) => <DownloadTaskCard key={job.id} job={job} />)}</div> : <p className="download-empty">{t("jobsEmpty")}</p>}
    </div>
  );
}
