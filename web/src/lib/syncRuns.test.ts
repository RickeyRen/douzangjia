import { expect, it } from "vitest";

import type { SyncRun } from "../app/api";
import { splitSyncRuns } from "./syncRuns";

const run = (id: number, values: Partial<SyncRun> = {}): SyncRun => ({
  id,
  mode: "incremental",
  phase: "done",
  status: "completed",
  discovered: 75,
  enqueued: 0,
  errorCode: null,
  startedAt: 1000 - id,
  finishedAt: 1000,
  ...values,
});

it("folds routine checks and keeps runs that did something", () => {
  const runs = [run(1), run(2, { enqueued: 3 }), run(3), run(4, { status: "failed", errorCode: "X" }), run(5, { mode: "full" }), run(6)];
  const { notable, quiet, quietSince } = splitSyncRuns(runs);
  expect(notable.map((entry) => entry.id)).toEqual([2, 4, 5]);
  expect(quiet).toBe(3);
  expect(quietSince).toBe(994);
});
