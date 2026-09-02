import {
  ArrowClockwise,
  CheckCircle,
  CloudArrowDown,
  Pulse,
} from "@phosphor-icons/react";

import type { DashboardActivity, DownloadJob } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { formatBytes, formatSpeed } from "../status/downloadFormat";
import { DashboardSection } from "./DashboardPrimitives";

function progress(job: DownloadJob): number | null {
  if (job.totalBytes === null || job.totalBytes <= 0) return null;
  return Math.min(100, Math.max(0, Math.round(job.downloadedBytes / job.totalBytes * 100)));
}

export function LiveActivitySection({
  activity,
  speedBps,
  onOpenDownloads,
}: {
  activity: DashboardActivity;
  speedBps: number;
  onOpenDownloads: () => void;
}) {
  const { t } = useI18n();
  const active = activity.state !== "idle";
  const headline = {
    syncing_and_downloading: t("activitySyncingAndDownloading"),
    syncing: t("activitySyncing"),
    downloading: t("activityDownloading"),
    idle: t("activityIdle"),
  }[activity.state];
  const sync = activity.sync;
  const syncActive = sync?.status === "queued" || sync?.status === "running";
  const syncMode = sync?.mode === "full" ? t("activityFullSync") : t("activityIncrementalSync");
  const syncPhase = sync?.phase === "discovering"
    ? t("activityDiscovering")
    : sync?.status === "queued"
      ? t("activityQueued")
      : t("activityFinished");
  const sourceNames = activity.sources.map((source) => source.name).join(" · ");

  return (
    <DashboardSection title={t("liveActivityTitle")} className="home-activity-section bento-hero" testId="dashboard-hero">
      <div className={`home-activity${active ? " is-active" : ""}`} role="region" aria-label={t("liveActivityTitle")}>
        <div className="home-activity-summary">
          <span className="home-activity-orbit" data-icon-tone={active ? "cyan" : "green"}>
            {active ? <Pulse size={24} weight="duotone" /> : <CheckCircle size={24} weight="duotone" />}
          </span>
          <div className="home-activity-copy">
            <span className="home-activity-live"><i />{t("activityLive")}</span>
            <strong>{headline}</strong>
            <p>{active
              ? sourceNames || (syncActive ? `${syncMode} · ${syncPhase}` : t("activityQueueSummary"))
              : t("activityIdleDetail")}</p>
          </div>
          <dl className="home-activity-stats">
            <div><dt>{t("currentSpeed")}</dt><dd>{formatSpeed(speedBps)}</dd></div>
            <div><dt>{t("activeDownloads")}</dt><dd>{activity.downloads.length}</dd></div>
          </dl>
        </div>

        <div className="home-activity-list">
          {sync ? (
            <article className={`home-activity-row is-sync${syncActive ? " is-running" : ""}`}>
              <span className="app-icon-well" data-icon-tone="violet">
                <ArrowClockwise size={19} weight="duotone" />
              </span>
              <div className="home-activity-row-copy">
                <strong>{syncActive ? `${syncMode} · ${syncPhase}` : t("activityRecentSync")}</strong>
                <small>{sourceNames || syncPhase}</small>
              </div>
              <span className="home-activity-counts">
                {t("activityDiscovered")} {sync.discovered} · {t("activityEnqueued")} {sync.enqueued}
              </span>
              {syncActive ? <i className="home-activity-scan" /> : null}
            </article>
          ) : null}

          {activity.downloads.map((job) => {
            const percent = progress(job);
            const subtitle = [job.author, ...job.collections].filter(Boolean).join(" · ");
            return (
              <button className="home-activity-row is-download" type="button" key={job.id} onClick={onOpenDownloads}>
                <span className="app-icon-well" data-icon-tone="blue"><CloudArrowDown size={19} weight="duotone" /></span>
                <span className="home-activity-row-copy">
                  <strong>{job.description || t("activityNoTitle")}</strong>
                  <small>{subtitle}</small>
                </span>
                <span className="home-activity-download-metrics">
                  <strong>{formatBytes(job.downloadedBytes)} / {job.totalBytes === null ? t("totalUnknown") : formatBytes(job.totalBytes)}</strong>
                  <small>{formatSpeed(job.speedBps)}</small>
                </span>
                <span
                  className={`home-activity-progress${percent === null ? " is-indeterminate" : ""}`}
                  role="progressbar"
                  aria-label={`${job.description || t("activityNoTitle")} ${t("activityDownloadProgress")}`}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={percent ?? undefined}
                >
                  <i style={percent === null ? undefined : { width: `${percent}%` }} />
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </DashboardSection>
  );
}
