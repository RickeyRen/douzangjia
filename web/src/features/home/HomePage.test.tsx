import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { ThemeProvider } from "../../theme/ThemeProvider";
import { HomePage } from "./HomePage";

const snapshot = {
  storage: {
    totalBytes: 1_000_000_000,
    usedBytes: 420_000_000,
    freeBytes: 580_000_000,
    archiveBytes: 120_000_000,
    usedPercent: 42,
  },
  system: {
    cpuCount: 4,
    cpuLoadPercent: 18.5,
    loadAverage1m: 0.74,
    loadAverage5m: 0.62,
    loadAverage15m: 0.58,
    memoryTotalBytes: 8_000_000_000,
    memoryUsedBytes: 3_000_000_000,
    processMemoryBytes: 180_000_000,
  },
  library: {
    items: 1600,
    archivedItems: 1569,
    mediaFiles: 3717,
    creators: 328,
    sources: 14,
    completeSources: 3,
    incompleteSources: 6,
    neverSyncedSources: 5,
    discoveredLinks: 2300,
    archivedBytes: 120_000_000,
  },
  queue: {
    pending: 2,
    running: 1,
    retry: 1,
    failed: 0,
    completed: 1569,
    downloadedBytes: 15_429_894,
    totalBytes: 50_000_000,
    speedBps: 1_240_000,
    etaSeconds: 28,
  },
  health: { recentErrors: 2, uptimeSeconds: 3600, latestSync: null },
  account: {
    sessionStored: true,
    status: "healthy",
    lastVerifiedAt: 100,
    lastSyncAt: 90,
    lastFailureAt: null,
    errorCode: null,
    consecutiveFailures: 0,
    account: {
      id: "self-id",
      nickname: "天鹰座裂缝之外",
      uniqueId: "sky-gap",
      avatarUrl: null,
    },
  },
  sources: [
    {
      id: "favorite_collection:travel",
      kind: "favorite_collection",
      name: "想去的地方",
      autoDownloadEnabled: true,
      downloadPolicyUpdatedAt: 90,
      discovered: 120,
      archived: 84,
      pending: 2,
      running: 1,
      retry: 0,
      failed: 0,
      archivedBytes: 80_000_000,
      knownTotalBytes: 80_000_000,
      remoteTotal: 120,
      remoteComplete: true,
      coveragePercent: 70,
      syncStatus: "complete",
      lastSyncAt: 90,
      errorCode: null,
    },
  ],
  generatedAt: 100,
} as const;

vi.mock("./useDashboardStream", () => ({
  useDashboardStream: () => ({
    snapshot,
    series: [
      {
        sampledAt: 90,
        downloadSpeedBps: 400_000,
        downloadedBytes: 100,
        cpuLoadPercent: 10,
        memoryUsedBytes: 2_000_000_000,
        processMemoryBytes: 100_000_000,
        diskUsedBytes: 400_000_000,
        diskFreeBytes: 600_000_000,
        archiveBytes: 100_000_000,
      },
      {
        sampledAt: 100,
        downloadSpeedBps: 1_240_000,
        downloadedBytes: 200,
        cpuLoadPercent: 18.5,
        memoryUsedBytes: 3_000_000_000,
        processMemoryBytes: 180_000_000,
        diskUsedBytes: 420_000_000,
        diskFreeBytes: 580_000_000,
        archiveBytes: 120_000_000,
      },
    ],
    connected: true,
    loading: false,
    error: false,
  }),
}));

vi.mock("../../app/api", async () => {
  const actual = await vi.importActual<typeof import("../../app/api")>(
    "../../app/api",
  );
  return { ...actual, updateSourceDownloadPolicy: vi.fn() };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("renders a full live home with account, charts, storage, and source progress", () => {
  render(<ThemeProvider><HomePage onOpenDownloads={vi.fn()} onOpenSource={vi.fn()} /></ThemeProvider>);

  const home = screen.getByRole("main", { name: "首页" });
  expect(within(home).getAllByText("天鹰座裂缝之外")).toHaveLength(2);
  expect(within(home).getByText("抖音连接健康")).toBeVisible();
  expect(within(home).getAllByText("1.2 MB/s")).toHaveLength(2);
  expect(within(home).getByText("3,717")).toBeVisible();
  expect(within(home).getByRole("img", { name: "下载速度趋势" })).toBeVisible();
  expect(within(home).getByRole("img", { name: "系统负载趋势" })).toBeVisible();
  expect(within(home).getByRole("region", { name: "类目下载进度" })).toBeVisible();
});

it("changes one category download policy without changing another source", async () => {
  const user = userEvent.setup();
  vi.mocked(api.updateSourceDownloadPolicy).mockResolvedValue({
    ...snapshot.sources[0],
    autoDownloadEnabled: false,
  });
  render(<ThemeProvider><HomePage onOpenDownloads={vi.fn()} onOpenSource={vi.fn()} /></ThemeProvider>);

  const toggle = screen.getByRole("switch", { name: "自动下载 想去的地方" });
  expect(toggle).toBeChecked();
  await user.click(toggle);

  expect(api.updateSourceDownloadPolicy).toHaveBeenCalledWith(
    "favorite_collection:travel",
    false,
  );
});
