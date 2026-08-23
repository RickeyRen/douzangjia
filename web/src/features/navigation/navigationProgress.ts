import type { DashboardSnapshot, DownloadSummary, LibrarySource, SyncRun } from "../../app/api";
import type { ProgressRingState } from "../../components/ProgressRing";

function percentage(completed: number, total: number | null | undefined): number {
  if (!total || total <= 0) return completed > 0 ? 100 : 0;
  return Math.round(Math.min(100, Math.max(0, (completed / total) * 100)));
}

export function sourceDownloadProgress(source: LibrarySource, dashboard: DashboardSnapshot | null): number {
  const liveSource = dashboard?.sources.find((entry) => entry.id === source.id);
  if (liveSource) return Math.round(Math.min(100, Math.max(0, liveSource.coveragePercent)));
  return percentage(source.archivedCount, source.discoveredCount);
}

export function totalDownloadProgress(summary: DownloadSummary | null | undefined): number {
  if (!summary) return 0;
  if (summary.totalBytes !== null && summary.totalBytes > 0) {
    return percentage(summary.downloadedBytes, summary.totalBytes);
  }
  const totalJobs = summary.pending + summary.running + summary.retry + summary.failed + summary.completed;
  return percentage(summary.completed, totalJobs);
}

export function syncProgressState(run: SyncRun | null | undefined): ProgressRingState {
  if (!run) return "idle";
  if (["running", "queued", "pending", "starting"].includes(run.status)) return "running";
  if (["completed", "complete", "success", "succeeded"].includes(run.status)) return "complete";
  if (["failed", "error", "cancelled", "canceled"].includes(run.status)) return "failed";
  return run.finishedAt ? "complete" : "running";
}
