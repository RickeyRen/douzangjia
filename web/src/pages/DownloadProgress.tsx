import { ArrowClockwise, CaretRight, CloudArrowDown, Pause, Play, Stop, WarningCircle } from "@phosphor-icons/react";
import { useState } from "react";

import { controlArchiveBatch, retryFailedDownloads, type ArchiveProgress, type ArchiveProgressItem } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { routeHref } from "../app/router";
import { formatBytes, formatEta, formatInteger, formatSpeed } from "../lib/format";
import { errorSuffix } from "../lib/health";
import { refreshArchiveProgress } from "../lib/useArchiveProgress";
import { Progress, Spinner } from "../ui/primitives";
import { t } from "../i18n/t";

type Variant = "home" | "full";

/** The one place that answers "how far along is saving everything to the NAS". */
export function DownloadProgress({ progress, variant }: { progress: ArchiveProgress; variant: Variant }) {
  const active = progress.active;
  if (active) return <ActiveDownload progress={progress} variant={variant} />;
  if (progress.failedTotal > 0) return <FailedDownloads progress={progress} variant={variant} />;
  return null;
}

function ActiveDownload({ progress, variant }: { progress: ArchiveProgress; variant: Variant }) {
  const { toast } = useAppData();
  const [busy, setBusy] = useState(false);
  const active = progress.active!;
  const paused = active.status === "paused";
  const settled = active.completedItems + active.failedItems;
  const percent = active.totalItems ? (active.completedItems / active.totalItems) * 100 : 0;
  const labels = active.batches.map((batch) => batch.label).join("、");

  async function control(action: "pause" | "resume" | "cancel") {
    if (action === "cancel" && !window.confirm(t("停止下载剩下的 {n} 个作品？已经存好的会保留。", { n: formatInteger(active.totalItems - settled) }))) return;
    setBusy(true);
    try {
      const targets = active.batches.filter((batch) => (action === "resume" ? batch.status === "paused" : batch.status !== "paused" || action === "cancel"));
      await Promise.all(targets.map((batch) => controlArchiveBatch(batch.id, action)));
      await refreshArchiveProgress();
    } catch {
      toast(t("操作失败"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={`download-card${variant === "home" ? " is-home" : ""}${paused ? " is-paused" : ""}`} aria-label={t("下载进度")}>
      <div className="download-head">
        <span className="download-icon">{busy ? <Spinner size={18} /> : <CloudArrowDown size={22} weight="fill" />}</span>
        <div className="download-title">
          <strong>{paused ? t("已暂停存到 NAS") : t("正在存到 NAS")}</strong>
          <small>{labels}</small>
        </div>
        <div className="download-controls">
          {paused ? (
            <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => void control("resume")}>
              <Play size={14} weight="fill" />
              {t("继续")}
            </button>
          ) : (
            <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => void control("pause")}>
              <Pause size={14} weight="fill" />
              {t("暂停")}
            </button>
          )}
          <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void control("cancel")}>
            <Stop size={14} weight="fill" />
            {t("停止")}
          </button>
        </div>
      </div>

      <div className="download-meter">
        <strong className="download-percent num">{Math.floor(percent)}%</strong>
        <span className="num">
          {t("已完成 {done} / {total} 个作品", { done: formatInteger(active.completedItems), total: formatInteger(active.totalItems) })}
        </span>
      </div>
      <Progress value={percent} tone={paused ? "warning" : "info"} />

      <dl className="download-facts">
        <div>
          <dt>{t("已下载")}</dt>
          <dd className="num">
            {formatBytes(active.downloadedBytes)}
            {active.estimatedTotalBytes ? <small> / {t("约 {size}", { size: formatBytes(active.estimatedTotalBytes) })}</small> : null}
          </dd>
        </div>
        <div>
          <dt>{t("速度")}</dt>
          <dd className="num">{paused ? "—" : formatSpeed(active.speedBps)}</dd>
        </div>
        <div>
          <dt>{t("预计还要")}</dt>
          <dd className="num">{paused ? t("已暂停") : active.etaSeconds ? formatEta(active.etaSeconds) : t("估算中…")}</dd>
        </div>
        <div>
          <dt>{t("排队 / 失败")}</dt>
          <dd className="num">
            {formatInteger(active.waitingItems)} / <span className={active.failedItems ? "text-danger" : undefined}>{formatInteger(active.failedItems)}</span>
          </dd>
        </div>
      </dl>

      {active.current.length ? (
        <div className="download-current">
          {active.current.slice(0, variant === "home" ? 3 : 4).map((item) => (
            <CurrentItem key={item.remoteId} item={item} />
          ))}
        </div>
      ) : !paused ? (
        <p className="download-note">{t("正在准备下一个作品…")}</p>
      ) : null}

      {variant === "home" ? (
        <a className="download-link" href={routeHref({ name: "activity" })}>
          {progress.failedTotal ? t("{n} 个下载失败，去状态页重试", { n: formatInteger(progress.failedTotal) }) : t("查看详细进度")}
          <CaretRight size={13} weight="bold" />
        </a>
      ) : progress.failedTotal ? (
        <FailureList progress={progress} />
      ) : null}
    </section>
  );
}

function CurrentItem({ item }: { item: ArchiveProgressItem }) {
  const [failed, setFailed] = useState(false);
  const percent = item.totalBytes ? (item.downloadedBytes / item.totalBytes) * 100 : 0;
  return (
    <div className="download-item">
      {item.coverUrl && !failed ? <img src={item.coverUrl} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} /> : <span className="download-item-cover" />}
      <div>
        <strong>{item.description || `@${item.author}`}</strong>
        <small className="num">
          {formatBytes(item.downloadedBytes)}
          {item.totalBytes ? ` / ${formatBytes(item.totalBytes)}` : ""}
        </small>
        <Progress value={percent} tone="info" />
      </div>
    </div>
  );
}

function FailedDownloads({ progress, variant }: { progress: ArchiveProgress; variant: Variant }) {
  if (variant === "home") {
    return (
      <section className="cta cta-warning">
        <WarningCircle size={22} weight="fill" className="cta-icon" />
        <div>
          <strong>{t("{n} 个作品没能存到 NAS", { n: formatInteger(progress.failedTotal) })}</strong>
          <p>{t("通常是网络或抖音临时出错，重试一般就能下好。")}</p>
        </div>
        <RetryButton count={progress.failedTotal} />
      </section>
    );
  }
  return (
    <section className="download-card is-failed" aria-label={t("下载失败")}>
      <FailureList progress={progress} />
    </section>
  );
}

function FailureList({ progress }: { progress: ArchiveProgress }) {
  const [open, setOpen] = useState(false);
  const shown = open ? progress.failures : progress.failures.slice(0, 3);
  return (
    <div className="download-failures">
      <div className="download-failures-head">
        <div>
          <strong>
            <WarningCircle size={16} weight="fill" /> {t("{n} 个作品下载失败", { n: formatInteger(progress.failedTotal) })}
          </strong>
          <small>{t("已自动重试过几次仍未成功")}</small>
        </div>
        <RetryButton count={progress.failedTotal} />
      </div>
      <ul>
        {shown.map((failure) => (
          <li key={failure.remoteId}>
            <span>{failure.description || `@${failure.author}`}</span>
            <small>
              @{failure.author}
              {errorSuffix(failure.errorCode)}
            </small>
          </li>
        ))}
      </ul>
      {progress.failures.length > 3 ? (
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen((value) => !value)}>
          {open ? t("收起") : t("显示更多")}
        </button>
      ) : null}
    </div>
  );
}

function RetryButton({ count }: { count: number }) {
  const { toast } = useAppData();
  const [busy, setBusy] = useState(false);
  async function retry() {
    setBusy(true);
    try {
      const result = await retryFailedDownloads();
      toast(t("已重新加入 {n} 个作品", { n: formatInteger(result.retried) }));
      await refreshArchiveProgress();
    } catch {
      toast(t("重试失败，请稍后再试"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => void retry()}>
      {busy ? <Spinner size={14} /> : <ArrowClockwise size={14} weight="bold" />}
      {count > 1 ? t("全部重试") : t("重试")}
    </button>
  );
}
