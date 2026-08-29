import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import type { DashboardSnapshot } from "../../app/api";
import { ThemeProvider } from "../../theme/ThemeProvider";
import { HomePage } from "./HomePage";

const snapshot: DashboardSnapshot = {
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
    browserProcessCount: 5,
    browserMemoryBytes: 320_000_000,
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
  throughput: {
    today: { bytes: 20_000_000, previousBytes: 10_000_000, deltaBytes: 10_000_000, comparisonAvailable: true },
    sevenDays: { bytes: 80_000_000, previousBytes: 0, deltaBytes: 80_000_000, comparisonAvailable: false },
    thirtyDays: { bytes: 120_000_000, previousBytes: 0, deltaBytes: 120_000_000, comparisonAvailable: false },
    lifetime: { bytes: 120_000_000 },
    historyStartedAt: 1,
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
  runtime: {
    serviceCount: 3,
    application: {
      status: "running",
      memoryBytes: 180_000_000,
      cpuLoadPercent: 18.5,
      uptimeSeconds: 3600,
      lastActivityAt: 100,
    },
    downloader: {
      status: "running",
      workerCount: 2,
      activeWorkers: 2,
      activeDownloads: 1,
      pendingDownloads: 3,
      speedBps: 1_240_000,
      lastActivityAt: 99,
    },
    browser: {
      status: "busy",
      started: true,
      busy: true,
      processCount: 5,
      memoryBytes: 320_000_000,
      lastActivityAt: 90,
    },
  },
  generatedAt: 100,
};

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

it("renders the complete real operations dashboard in scan order", () => {
  render(<ThemeProvider><HomePage onOpenDownloads={vi.fn()} onOpenSource={vi.fn()} /></ThemeProvider>);

  const home = screen.getByRole("main", { name: "首页" });
  for (const heading of [
    "归档引擎使用情况",
    "服务详情",
    "归档吞吐",
    "队列状态",
    "NAS 系统",
    "资料库",
    "抖音账号",
    "收藏分类进度",
    "Runtime",
  ]) {
    expect(within(home).getByRole("heading", { name: heading })).toBeVisible();
  }
  expect(within(home).getAllByText("天鹰座裂缝之外").length).toBeGreaterThanOrEqual(1);
  expect(within(home).getByText("sky-gap")).toBeVisible();
  expect(within(home).getAllByText("1.2 MB/s").length).toBeGreaterThanOrEqual(1);
  expect(within(home).getByText("3,717")).toBeVisible();
  expect(within(home).getByRole("img", { name: "下载速度趋势" })).toBeVisible();
  expect(within(home).getByRole("img", { name: "系统负载趋势" })).toBeVisible();
  expect(within(home).getByRole("region", { name: "收藏分类进度" })).toBeVisible();
  expect(within(home).getByText("+9.5 MB")).toBeVisible();
  expect(within(home).getAllByText("数据积累中")).toHaveLength(2);
  expect(within(home).getByText("5 个进程")).toBeVisible();
});

it("uses distinct semantic icon tones instead of one accent everywhere", () => {
  render(<ThemeProvider><HomePage onOpenDownloads={vi.fn()} onOpenSource={vi.fn()} /></ThemeProvider>);

  const home = screen.getByRole("main", { name: "首页" });
  const tones = [...home.querySelectorAll<HTMLElement>("[data-icon-tone]")]
    .map((element) => element.dataset.iconTone);

  expect(new Set(tones).size).toBeGreaterThanOrEqual(5);
  expect(home.querySelector('[data-runtime-tone="blue"]')).toBeTruthy();
  expect(home.querySelector('[data-runtime-tone="violet"]')).toBeTruthy();
  expect(home.querySelector('[data-runtime-tone="green"]')).toBeTruthy();
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

it("keeps the last real snapshot visible when the live stream disconnects", () => {
  render(
    <ThemeProvider>
      <HomePage
        onOpenDownloads={vi.fn()}
        onOpenSource={vi.fn()}
        stream={{ snapshot, series: [], connected: false, loading: false, error: true }}
      />
    </ThemeProvider>,
  );

  expect(screen.getByText("实时数据正在重连")).toBeVisible();
  expect(screen.getByText("最后更新")).toBeVisible();
  expect(screen.getAllByText("1,569")[0]).toBeVisible();
});
