import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { useDashboardStream } from "./useDashboardStream";

vi.mock("../app/api", () => ({
  fetchDashboard: vi.fn(),
  fetchDashboardSeries: vi.fn(),
}));

const snapshot = {
  storage: { totalBytes: 1, usedBytes: 0, freeBytes: 1, archiveBytes: 0, usedPercent: 0 },
  system: { cpuCount: 1, cpuLoadPercent: 0, loadAverage1m: 0, loadAverage5m: 0, loadAverage15m: 0, memoryTotalBytes: 1, memoryUsedBytes: 0, processMemoryBytes: 0, browserProcessCount: 0, browserMemoryBytes: 0 },
  library: { items: 0, archivedItems: 0, mediaFiles: 0, creators: 0, sources: 0, completeSources: 0, incompleteSources: 0, neverSyncedSources: 0, discoveredLinks: 0, archivedBytes: 0 },
  queue: { pending: 0, running: 0, retry: 0, failed: 0, completed: 0, downloadedBytes: 0, totalBytes: 0, speedBps: 0, etaSeconds: 0 },
  throughput: {
    today: { bytes: 0, previousBytes: 0, deltaBytes: 0, comparisonAvailable: false },
    sevenDays: { bytes: 0, previousBytes: 0, deltaBytes: 0, comparisonAvailable: false },
    thirtyDays: { bytes: 0, previousBytes: 0, deltaBytes: 0, comparisonAvailable: false },
    lifetime: { bytes: 0 },
    historyStartedAt: null,
  },
  health: { recentErrors: 0, uptimeSeconds: 1, latestSync: null },
  activity: { state: "idle" as const, sync: null, sources: [], downloads: [] },
  account: { sessionStored: true, status: "healthy" as const, lastVerifiedAt: 1, lastSyncAt: 1, lastFailureAt: null, errorCode: null, consecutiveFailures: 0, account: null },
  runtime: {
    serviceCount: 3,
    application: { status: "running", memoryBytes: 0, cpuLoadPercent: 0, uptimeSeconds: 1, lastActivityAt: 1 },
    downloader: { status: "unavailable", workerCount: 0, activeWorkers: 0, activeDownloads: 0, pendingDownloads: 0, speedBps: 0, lastActivityAt: null },
    browser: { status: "unavailable", started: false, busy: false, processCount: 0, memoryBytes: 0, lastActivityAt: null },
  },
  sources: [],
  generatedAt: 1,
};

class FakeEventSource {
  static latest: FakeEventSource;
  static openings = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  listeners = new Map<string, EventListener>();

  constructor(readonly url: string) {
    FakeEventSource.latest = this;
    FakeEventSource.openings += 1;
  }

  addEventListener(type: string, listener: EventListener) {
    this.listeners.set(type, listener);
  }

  removeEventListener(type: string) {
    this.listeners.delete(type);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: object) {
    this.listeners.get(type)?.({ data: JSON.stringify(data) } as MessageEvent as unknown as Event);
  }
}

beforeEach(() => {
  FakeEventSource.openings = 0;
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.mocked(api.fetchDashboard).mockResolvedValue(snapshot);
  vi.mocked(api.fetchDashboardSeries).mockResolvedValue({ window: "24h", items: [] });
});

it("stays dormant when a parent already owns the dashboard stream", () => {
  const view = renderHook(() => useDashboardStream(false));

  expect(view.result.current.loading).toBe(false);
  expect(FakeEventSource.openings).toBe(0);
  expect(api.fetchDashboard).not.toHaveBeenCalled();
  expect(api.fetchDashboardSeries).not.toHaveBeenCalled();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

it("loads once, then follows SSE snapshots and closes the stream", async () => {
  const view = renderHook(() => useDashboardStream());

  await waitFor(() => expect(view.result.current.snapshot?.generatedAt).toBe(1));
  expect(FakeEventSource.latest.url).toBe("/api/events");
  act(() => {
    FakeEventSource.latest.emit("snapshot", {
      ...snapshot,
      generatedAt: 2,
      queue: { ...snapshot.queue, speedBps: 2048 },
    });
  });
  expect(view.result.current.snapshot?.queue.speedBps).toBe(2048);
  expect(view.result.current.connected).toBe(true);

  view.unmount();
  expect(FakeEventSource.latest.closed).toBe(true);
});

it("refreshes persisted trend points when a new five-second sample can exist", async () => {
  const nextPoint = {
    sampledAt: 6,
    downloadSpeedBps: 2048,
    downloadedBytes: 1024,
    cpuLoadPercent: 12,
    memoryUsedBytes: 300,
    processMemoryBytes: 100,
    diskUsedBytes: 400,
    diskFreeBytes: 600,
    archiveBytes: 50,
  };
  vi.mocked(api.fetchDashboardSeries)
    .mockResolvedValueOnce({ window: "24h", items: [] })
    .mockResolvedValueOnce({ window: "24h", items: [nextPoint] });
  const view = renderHook(() => useDashboardStream());
  await waitFor(() => expect(api.fetchDashboardSeries).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(view.result.current.snapshot?.generatedAt).toBe(1));

  act(() => {
    FakeEventSource.latest.emit("snapshot", { ...snapshot, generatedAt: 6 });
  });

  await waitFor(() => expect(view.result.current.series).toEqual([nextPoint]));
  expect(api.fetchDashboardSeries).toHaveBeenCalledTimes(2);
});

it("keeps the last persisted trend visible when a refresh fails", async () => {
  const previousPoint = {
    sampledAt: 1,
    downloadSpeedBps: 512,
    downloadedBytes: 256,
    cpuLoadPercent: 8,
    memoryUsedBytes: 300,
    processMemoryBytes: 100,
    diskUsedBytes: 400,
    diskFreeBytes: 600,
    archiveBytes: 50,
  };
  vi.mocked(api.fetchDashboardSeries)
    .mockResolvedValueOnce({ window: "24h", items: [previousPoint] })
    .mockRejectedValueOnce(new Error("series unavailable"));
  const view = renderHook(() => useDashboardStream());
  await waitFor(() => expect(view.result.current.series).toEqual([previousPoint]));

  act(() => {
    FakeEventSource.latest.emit("snapshot", { ...snapshot, generatedAt: 6 });
  });
  await waitFor(() => expect(api.fetchDashboardSeries).toHaveBeenCalledTimes(2));

  expect(view.result.current.series).toEqual([previousPoint]);
  expect(view.result.current.error).toBe(false);
});
