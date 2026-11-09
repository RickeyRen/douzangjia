import { ArrowClockwise, CaretRight, CloudArrowDown, Pause, Play, Stop, WarningCircle } from "@phosphor-icons/react";
import { useState } from "react";

import { controlArchiveBatch, plannedTotal, retryFailedDownloads, type ArchiveProgress, type ArchiveProgressItem } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { routeHref } from "../app/router";
import { formatBytes, formatEta, formatInteger, formatSpeed } from "../lib/format";
import { describeError, errorSuffix } from "../lib/health";
import { refreshArchiveProgress } from "../lib/useArchiveProgress";
import { Progress, Spinner } from "../ui/primitives";
import { t } from "../i18n/t";

type Variant = "home" | "full";

/**
 * The one place that answers "how far along is saving everything to the NAS".
 * On home the running batch and the failures are separate cards shown side by side.
 */
export function DownloadProgress({ progress, variant }: { progress: ArchiveProgress; variant: Variant }) {
  const active = progress.active;
  if (variant === "home") {
    return (
      <>
        {active ? <HomeActiveCard active={active} /> : null}
        {progress.failedTotal > 0 ? <HomeFailedCard progress={progress} /> : null}
      </>
    );
  }
  if (active) return <ActiveDownload progress={progress} />;
  if (progress.failedTotal > 0) return <FailedDownloads progress={progress} />;
  return null;
}

type ActiveBatch = NonNullable<ArchiveProgress["active"]>;

function useBatchControl(active: ActiveBatch) {
  const { toast } = useAppData();
  const [busy, setBusy] = useState(false);
  const settled = active.completedItems + active.failedItems;

  async function control(action: "pause" | "resume" | "cancel") {
    if (action === "cancel" && !window.confirm(t("停止下载剩下的 {n} 个作品？已经存好的会保留。", { n: formatInteger(plannedTotal(active) - settled) }))) return;
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
  return { busy, control };
}

function HomeActiveCard({ active }: { active: ActiveBatch }) {
  const { busy, control } = useBatchControl(active);
  const paused = active.status === "paused";
  const total = plannedTotal(active);
  const percent = total ? (active.completedItems / total) * 100 : 0;
  const labels = active.batches.map((batch) => batch.label).join("、");
  return (
    <section className={`card dl-card dl-prog${paused ? " is-paused" : ""}`} aria-label={t("下载进度")}>
      <div className="row-h">
        <span className="live">
          <i />
          {paused ? t("已暂停") : t("正在下载")}
        </span>
        {labels ? <span className="tag" title={labels}>“{labels}”</span> : null}
        <span className="sp" />
        {paused ? (
          <button type="button" className="ghost-btn" disabled={busy} onClick={() => void control("resume")}>
            {busy ? <Spinner size={12} /> : <Play size={12} weight="fill" />}
            {t("继续")}
          </button>
        ) : (
          <button type="button" className="ghost-btn" disabled={busy} onClick={() => void control("pause")}>
            {busy ? <Spinner size={12} /> : <Pause size={12} weight="fill" />}
            {t("暂停")}
          </button>
        )}
      </div>
      <div className="dl-n">
        <span className="num big">{formatInteger(active.completedItems)}</span>
        <span className="num of">/ {formatInteger(total)}</span>
        <span className="sp" />
        <span className="num pct">{percent >= 10 || percent === 0 ? Math.floor(percent) : percent.toFixed(1)}%</span>
      </div>
      <div className="pbar">
        <i style={{ width: `${Math.min(100, percent)}%` }} />
      </div>
      {active.queueing ? (
        <p className="dl-queueing">
          {t("还在加入下载队列：已加入 {queued} / {planned} 个", { queued: formatInteger(active.totalItems), planned: formatInteger(total) })}
        </p>
      ) : null}
      <div className="meta3">
        <div>
          <span>{t("速度")}</span>
          <b className="num">{paused ? "—" : formatSpeed(active.speedBps)}</b>
        </div>
        <div>
          <span>{t("每分钟")}</span>
          <b className="num">{paused || !active.itemsPerMinute ? "—" : t("{n} 个", { n: Math.round(active.itemsPerMinute) })}</b>
        </div>
        <div>
          <span>{t("预计剩余")}</span>
          <b className="num">{paused ? t("已暂停") : active.etaSeconds ? formatEta(active.etaSeconds) : t("估算中")}</b>
        </div>
      </div>
      <a className="dl-more" href={routeHref({ name: "activity" })}>
        {t("查看详细进度")}
        <CaretRight size={12} weight="bold" />
      </a>
    </section>
  );
}

function HomeFailedCard({ progress }: { progress: ArchiveProgress }) {
  const reasons = new Map<string, number>();
  for (const failure of progress.failures) {
    const reason = describeError(failure.errorCode);
    if (reason) reasons.set(reason, (reasons.get(reason) ?? 0) + 1);
  }
  const reason = [...reasons.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
  const covers = progress.failures.filter((failure) => failure.coverUrl).slice(0, 5);
  return (
    <section className="card dl-card dl-fail" aria-label={t("下载失败")}>
      <div className="row-h">
        <span className="warn">
          <WarningCircle size={17} weight="fill" />
        </span>
        <span className="sp" />
        <a className="num cnt" href={routeHref({ name: "activity" })} title={t("去下载页查看")}>
          {formatInteger(progress.failedTotal)}
        </a>
      </div>
      <h3>{t("{n} 个作品没能存到 NAS", { n: formatInteger(progress.failedTotal) })}</h3>
      <p>
        {reason ?? t("通常是网络或抖音临时出错")}
        <br />
        {t("稍后重试通常就能恢复")}
      </p>
      <div className="row-h end">
        <div className="thumb-stack">
          {covers.map((failure) => (
            <FailureCover key={failure.remoteId} src={failure.coverUrl!} />
          ))}
        </div>
        <span className="sp" />
        <RetryButton count={progress.failedTotal} className="btn-o" />
      </div>
    </section>
  );
}

function FailureCover({ src }: { src: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <span className="stack-th" />;
  return <img className="stack-th" src={src} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />;
}

function ActiveDownload({ progress }: { progress: ArchiveProgress }) {
  const active = progress.active!;
  const { busy, control } = useBatchControl(active);
  const paused = active.status === "paused";
  const total = plannedTotal(active);
  const percent = total ? (active.completedItems / total) * 100 : 0;
  const labels = active.batches.map((batch) => batch.label).join("、");

  return (
    <section className={`download-card${paused ? " is-paused" : ""}`} aria-label={t("下载进度")}>
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
          {t("已完成 {done} / {total} 个作品", { done: formatInteger(active.completedItems), total: formatInteger(total) })}
        </span>
        {active.queueing ? (
          <small className="dl-queueing">
            {t("还在加入下载队列：已加入 {queued} / {planned} 个", { queued: formatInteger(active.totalItems), planned: formatInteger(total) })}
          </small>
        ) : null}
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
          {active.current.slice(0, 4).map((item) => (
            <CurrentItem key={item.remoteId} item={item} />
          ))}
        </div>
      ) : !paused ? (
        <p className="download-note">{t("正在准备下一个作品…")}</p>
      ) : null}

      {progress.failedTotal ? <FailureList progress={progress} /> : null}
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

function FailedDownloads({ progress }: { progress: ArchiveProgress }) {
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

function RetryButton({ count, className = "btn btn-primary btn-sm" }: { count: number; className?: string }) {
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
    <button type="button" className={className} disabled={busy} onClick={() => void retry()}>
      {busy ? <Spinner size={14} /> : <ArrowClockwise size={14} weight="bold" />}
      {count > 1 ? t("全部重试") : t("重试")}
    </button>
  );
}
