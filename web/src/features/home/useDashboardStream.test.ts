import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { useDashboardStream } from "./useDashboardStream";

vi.mock("../../app/api", () => ({
  fetchDashboard: vi.fn(),
  fetchDashboardSeries: vi.fn(),
}));

const snapshot = {
  storage: { totalBytes: 1, usedBytes: 0, freeBytes: 1, archiveBytes: 0, usedPercent: 0 },
  system: { cpuCount: 1, cpuLoadPercent: 0, loadAverage1m: 0, loadAverage5m: 0, loadAverage15m: 0, memoryTotalBytes: 1, memoryUsedBytes: 0, processMemoryBytes: 0 },
  library: { items: 0, archivedItems: 0, mediaFiles: 0, creators: 0, sources: 0, completeSources: 0, incompleteSources: 0, neverSyncedSources: 0, discoveredLinks: 0, archivedBytes: 0 },
  queue: { pending: 0, running: 0, retry: 0, failed: 0, completed: 0, downloadedBytes: 0, totalBytes: 0, speedBps: 0, etaSeconds: 0 },
  health: { recentErrors: 0, uptimeSeconds: 1, latestSync: null },
  account: { sessionStored: true, status: "healthy" as const, lastVerifiedAt: 1, lastSyncAt: 1, lastFailureAt: null, errorCode: null, consecutiveFailures: 0, account: null },
  sources: [],
  generatedAt: 1,
};

class FakeEventSource {
  static latest: FakeEventSource;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  listeners = new Map<string, EventListener>();

  constructor(readonly url: string) {
    FakeEventSource.latest = this;
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
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.mocked(api.fetchDashboard).mockResolvedValue(snapshot);
  vi.mocked(api.fetchDashboardSeries).mockResolvedValue({ window: "24h", items: [] });
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
