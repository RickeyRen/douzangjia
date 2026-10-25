import {
  ArrowClockwise,
  CheckCircle,
  CloudArrowDown,
  HardDrives,
  Pause,
  Play,
  Pulse,
  Stop,
  Warning,
  WarningCircle,
} from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import {
  controlArchiveBatch,
  fetchArchiveBatches,
  fetchJobs,
  fetchSyncRuns,
  triggerSync,
  updateSourceDownloadPolicy,
  type ArchiveBatch,
  type DownloadSnapshot,
  type SourceProgress,
  type SyncRun,
} from "../app/api";
import { useAppData } from "../app/appDataContext";
import { routeHref } from "../app/router";
import { formatBytes, formatDateTime, formatEta, formatInteger, formatRelative, formatSpeed } from "../lib/format";
import { describeHealth, errorSuffix } from "../lib/health";
import { useDashboardStream } from "../lib/useDashboardStream";
import { sourceLabel } from "../shell/sourceMeta";
import { PageHeader, Progress, Spinner, Switch } from "../ui/primitives";
import { t } from "../i18n/t";

const JOB_STATUS: Record<string, { text: string; tone: string }> = {
  running: { text: t("下载中"), tone: "badge-info" },
  pending: { text: t("排队中"), tone: "" },
  retry: { text: t("等待重试"), tone: "badge-warning" },
  failed: { text: t("失败"), tone: "badge-danger" },
  completed: { text: t("完成"), tone: "badge-success" },
};

const RUN_STATUS: Record<string, { text: string; tone: string }> = {
  completed: { text: t("完成"), tone: "badge-success" },
  failed: { text: t("失败"), tone: "badge-danger" },
  running: { text: t("进行中"), tone: "badge-info" },
  queued: { text: t("排队中"), tone: "" },
  partial: { text: t("部分完成"), tone: "badge-warning" },
};

const BATCH_KIND: Record<string, string> = { item: "单个作品", source: "来源", creator: "博主", selection: "手动选择", missing: "全部未存作品" };

function usePolling<T>(load: () => Promise<T>, intervalMs: number): T | null {
  const [value, setValue] = useState<T | null>(null);
  useEffect(() => {
    let active = true;
    const tick = () =>
      load()
        .then((next) => active && setValue(next))
        .catch(() => undefined);
    void tick();
    const timer = window.setInterval(tick, intervalMs);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
    // The loaders are module-level API calls, so the interval never needs rebuilding.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs]);
  return value;
}

export function ActivityPage() {
  const { health, refreshHealth, requestDouyinLogin, toast } = useAppData();
  const stream = useDashboardStream();
  const jobs = usePolling<DownloadSnapshot>(fetchJobs, 2000);
  const runs = usePolling<{ items: SyncRun[] }>(fetchSyncRuns, 8000);
  const [batches, setBatches] = useState<ArchiveBatch[]>([]);
  const [syncing, setSyncing] = useState<"quick" | "full" | null>(null);
  const view = describeHealth(health);
  const snapshot = stream.snapshot;

  useEffect(() => {
    let active = true;
    const load = () => fetchArchiveBatches().then((page) => active && setBatches(page.items)).catch(() => undefined);
    void load();
    const timer = window.setInterval(load, 4000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  async function sync(full: boolean) {
    setSyncing(full ? "full" : "quick");
    try {
      await triggerSync(full);
      toast(full ? t("已开始全量同步，会重新核对所有来源") : t("已开始同步"));
      window.setTimeout(() => void refreshHealth(), 3000);
    } catch {
      toast(t("无法开始同步"));
    } finally {
      setSyncing(null);
    }
  }

  async function control(batch: ArchiveBatch, action: "pause" | "resume" | "cancel") {
    try {
      const updated = await controlArchiveBatch(batch.id, action);
      setBatches((current) => current.map((entry) => (entry.id === batch.id ? { ...entry, ...updated } : entry)));
    } catch {
      toast(t("操作失败"));
    }
  }

  const HealthGlyph = view.tone === "ok" ? CheckCircle : view.tone === "busy" ? Pulse : view.tone === "warning" ? Warning : WarningCircle;
  const summary = jobs?.summary;
  const activeJobs = (jobs?.items ?? []).filter((job) => job.status !== "completed").slice(0, 12);
  const activeBatches = batches.filter((batch) => !["completed", "cancelled"].includes(batch.status)).slice(0, 6);

  return (
    <>
      <PageHeader title={t("同步与下载")} subtitle="抖藏家会每隔几分钟检查一次新收藏，并按来源设置把作品存到 NAS。" />
      <div className="columns">
        <div className="stack">
          <section className="panel">
            <div className="health">
              <span className={`health-icon is-${view.tone}`}>
                <HealthGlyph size={26} weight="fill" />
              </span>
              <div className="health-text">
                <strong>{view.title}</strong>
                <p>{view.body}</p>
              </div>
            </div>
            <div className="metric-row">
              <div className="metric">
                <span>{t("上次成功同步")}</span>
                <strong>{formatRelative(health?.lastSuccessAt)}</strong>
              </div>
              <div className="metric">
                <span>{t("检查间隔")}</span>
                <strong>{health ? t("{n} 分钟", { n: Math.round(health.intervalSeconds / 60) }) : "—"}</strong>
              </div>
              <div className="metric">
                <span>{t("后台浏览器")}</span>
                <strong>{health ? BROWSER_TEXT[health.browser] ?? health.browser : "—"}</strong>
              </div>
            </div>
            <div className="action-row">
              {view.action === "login" ? (
                <button type="button" className="btn btn-primary btn-sm" onClick={requestDouyinLogin}>
                  {t("重新扫码登录")}
                </button>
              ) : null}
              <button type="button" className={`btn btn-sm ${view.action === "sync" ? "btn-primary" : "btn-secondary"}`} disabled={syncing !== null} onClick={() => void sync(false)}>
                {syncing === "quick" ? <Spinner size={14} /> : <ArrowClockwise size={15} weight="bold" />}
                {t("立即同步")}
              </button>
              <button type="button" className="btn btn-ghost btn-sm" disabled={syncing !== null} onClick={() => void sync(true)}>
                {syncing === "full" ? <Spinner size={14} /> : null}
                {t("全量核对")}
              </button>
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>{t("下载队列")}</h2>
                <p>
                  {summary
                    ? t("{running} 个进行中 · {pending} 个排队 · {retry} 个待重试", { running: summary.running, pending: summary.pending, retry: summary.retry }) + (summary.failed ? t(" · {n} 个失败", { n: summary.failed }) : "")
                    : t("正在读取…")}
                </p>
              </div>
              {summary && summary.running > 0 ? (
                <span className="badge badge-info num">
                  {formatSpeed(summary.speedBps)} · 剩余 {formatEta(summary.etaSeconds)}
                </span>
              ) : null}
            </div>
            {activeJobs.length === 0 ? (
              <p className="empty-note">{t("队列是空的，所有作品都处理完了。")}</p>
            ) : (
              <div className="rows">
                {activeJobs.map((job) => {
                  const status = JOB_STATUS[job.status] ?? { text: job.status, tone: "" };
                  const percent = job.totalBytes ? (job.downloadedBytes / job.totalBytes) * 100 : 0;
                  return (
                    <div key={job.id} className="row">
                      <div className="row-main">
                        <strong>{job.description || `@${job.author}`}</strong>
                        <small>
                          @{job.author}
                          {errorSuffix(job.errorCode)}
                          {job.status === "retry" ? t(" · 第 {n} 次尝试", { n: job.attempts }) : ""}
                        </small>
                        {job.status === "running" ? <Progress value={percent} tone="info" /> : null}
                      </div>
                      <div className="row-side">
                        <span className={`badge ${status.tone}`}>{status.text}</span>
                        {job.status === "running" ? (
                          <div className="row-side-detail">
                            {formatBytes(job.downloadedBytes)} / {formatBytes(job.totalBytes)}
                          </div>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          {activeBatches.length ? (
            <section className="panel">
              <div className="panel-head">
                <div>
                  <h2>{t("收录任务")}</h2>
                  <p>{t("手动发起的“全部存到 NAS”和博主收录")}</p>
                </div>
              </div>
              <div className="rows">
                {activeBatches.map((batch) => {
                  const done = batch.completedCount ?? 0;
                  const total = batch.discoveredCount ?? 0;
                  return (
                    <div key={batch.id} className="row">
                      <div className="row-main">
                        <strong>
                          {BATCH_KIND[batch.kind] ?? batch.kind} · {batch.targetId}
                        </strong>
                        <small>
                          {formatInteger(done)} / {formatInteger(total)} 已完成
                          {batch.failedCount ? t(" · {n} 个失败", { n: batch.failedCount }) : ""}
                          {errorSuffix(batch.errorCode)}
                        </small>
                        <Progress value={total ? (done / total) * 100 : 0} tone="info" />
                      </div>
                      <div className="row-controls">
                        {batch.status === "paused" ? (
                          <button type="button" className="icon-btn icon-btn-sm" aria-label={t("继续")} onClick={() => void control(batch, "resume")}>
                            <Play size={15} weight="fill" />
                          </button>
                        ) : (
                          <button type="button" className="icon-btn icon-btn-sm" aria-label={t("暂停")} onClick={() => void control(batch, "pause")}>
                            <Pause size={15} weight="fill" />
                          </button>
                        )}
                        <button type="button" className="icon-btn icon-btn-sm" aria-label={t("取消")} onClick={() => void control(batch, "cancel")}>
                          <Stop size={15} weight="fill" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          ) : null}

          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>{t("最近同步")}</h2>
                <p>{t("每次检查新收藏的记录")}</p>
              </div>
            </div>
            {!runs ? (
              <div className="empty-note">
                <Spinner />
              </div>
            ) : runs.items.length === 0 ? (
              <p className="empty-note">{t("还没有同步记录。")}</p>
            ) : (
              <div className="rows">
                {runs.items.slice(0, 8).map((run) => {
                  const status = RUN_STATUS[run.status] ?? { text: run.status, tone: "" };
                  return (
                    <div key={run.id} className="row">
                      <div className="row-main">
                        <strong>{run.mode === "full" ? t("全量核对") : t("增量同步")}</strong>
                        <small>
                          {formatDateTime(run.startedAt)} · 发现 {formatInteger(run.discovered)} · 新增下载 {formatInteger(run.enqueued)}
                          {errorSuffix(run.errorCode)}
                        </small>
                      </div>
                      <span className={`badge ${status.tone}`}>{status.text}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </section>
        </div>

        <div className="stack">
          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>{t("存储空间")}</h2>
                <p>{snapshot ? t("归档占用 {size}", { size: formatBytes(snapshot.storage.archiveBytes) }) : t("正在读取…")}</p>
              </div>
              <HardDrives size={20} className="panel-icon" />
            </div>
            {snapshot ? (
              <>
                <div className="meter-label">
                  <strong className="num">
                    {formatBytes(snapshot.storage.usedBytes)} / {formatBytes(snapshot.storage.totalBytes)}
                  </strong>
                  <span>剩余 {formatBytes(snapshot.storage.freeBytes)}</span>
                </div>
                <Progress value={snapshot.storage.usedPercent} tone={snapshot.storage.usedPercent >= 90 ? "warning" : "info"} />
                <div className="metric-row">
                  <div className="metric">
                    <span>CPU</span>
                    <strong>{snapshot.system.cpuLoadPercent}%</strong>
                  </div>
                  <div className="metric">
                    <span>{t("服务内存")}</span>
                    <strong>{formatBytes(snapshot.system.processMemoryBytes + snapshot.system.browserMemoryBytes)}</strong>
                  </div>
                  <div className="metric">
                    <span>{t("下载速度")}</span>
                    <strong>{formatSpeed(snapshot.queue.speedBps)}</strong>
                  </div>
                </div>
              </>
            ) : null}
          </section>

          <section className="panel">
            <div className="panel-head">
              <div>
                <h2>{t("来源与自动下载")}</h2>
                <p>{t("打开开关的来源，新作品会自动存到 NAS")}</p>
              </div>
              <CloudArrowDown size={20} className="panel-icon" />
            </div>
            {snapshot ? (
              <div className="rows">
                {snapshot.sources
                  .filter((source) => source.discovered > 0 || source.kind === "favorite_collection")
                  .map((source) => (
                    <SourcePolicyRow key={source.id} source={source} />
                  ))}
              </div>
            ) : (
              <div className="empty-note">
                <Spinner />
              </div>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

const BROWSER_TEXT: Record<string, string> = {
  ok: "运行中",
  not_started: "待命",
  disconnected: "已断开",
  unresponsive: "无响应",
};

function SourcePolicyRow({ source }: { source: SourceProgress }) {
  const { toast, refreshSources } = useAppData();
  const [enabled, setEnabled] = useState(source.autoDownloadEnabled);
  useEffect(() => setEnabled(source.autoDownloadEnabled), [source.autoDownloadEnabled]);

  async function change(next: boolean) {
    setEnabled(next);
    try {
      await updateSourceDownloadPolicy(source.id, next);
      void refreshSources();
    } catch {
      setEnabled(!next);
      toast(t("设置失败"));
    }
  }

  const percent = source.discovered ? (source.archived / source.discovered) * 100 : 0;
  return (
    <div className="row">
      <div className="row-main">
        <a href={routeHref({ name: "library", sourceId: source.id, filters: {} })}>
          <strong>{sourceLabel(source)}</strong>
        </a>
        <small>
          已存 {formatInteger(source.archived)} / {formatInteger(source.discovered)}
          {source.failed ? t(" · {n} 个失败", { n: source.failed }) : ""}
          {errorSuffix(source.errorCode)}
        </small>
        <Progress value={percent} tone={percent >= 99.5 ? "success" : "info"} />
      </div>
      <Switch checked={enabled} onChange={(next) => void change(next)} label={t("{name} 自动存到 NAS", { name: source.name })} />
    </div>
  );
}
