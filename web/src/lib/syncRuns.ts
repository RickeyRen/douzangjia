import type { SyncRun } from "../app/api";

/** Routine checks that found nothing new are folded into one line so real events stand out. */
export function splitSyncRuns(runs: SyncRun[]) {
  const notable = runs.filter((run) => run.status !== "completed" || run.enqueued > 0 || run.mode === "full");
  const quiet = runs.filter((run) => !notable.includes(run));
  return { notable: notable.slice(0, 6), quiet: quiet.length, quietSince: quiet.length ? Math.min(...quiet.map((run) => run.startedAt)) : null };
}
