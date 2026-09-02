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
  activity: {
    state: "syncing_and_downloading",
    sync: {
      id: 8,
      mode: "incremental",
      phase: "discovering",
      status: "running",
      discovered: 9,
      enqueued: 4,
      errorCode: null,
      startedAt: 90,
      finishedAt: null,
    },
    sources: [
      { id: "account:likes", kind: "like", name: "喜欢", discovered: 120, remoteTotal: 150 },
    ],
    downloads: [
      {
        id: 21,
        kind: "download",
        remoteId: "video-21",
        author: "旅行家",
        description: "海边日落",
        collections: ["想去的地方"],
        status: "running",
        attempts: 0,
        nextAttemptAt: 0,
        errorCode: null,
        updatedAt: 100,
        currentAssetIndex: 0,
        downloadedBytes: 25,
        totalBytes: 100,
        speedBps: 10,
        etaSeconds: 8,
        assets: [],
      },
    ],
  },
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
      remoteTotal: 150,
      remoteComplete: false,
      coveragePercent: 56,
      syncStatus: "incomplete",
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
    "实时活动",
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

it("organizes live data into the Credit Pros bento hierarchy", () => {
  render(<ThemeProvider><HomePage onOpenDownloads={vi.fn()} onOpenSource={vi.fn()} /></ThemeProvider>);

  const bento = screen.getByTestId("dashboard-bento");
  expect(bento).toContainElement(screen.getByTestId("dashboard-hero"));
  expect(bento).toContainElement(screen.getByTestId("dashboard-primary-metrics"));
  expect(screen.getByTestId("dashboard-storage-card")).toHaveAttribute("data-used-percent", "42");
  expect(screen.getByTestId("dashboard-queue-card")).toHaveTextContent("2");
});

it("shows the current sync source and per-video download progress", () => {
  render(<ThemeProvider><HomePage onOpenDownloads={vi.fn()} onOpenSource={vi.fn()} /></ThemeProvider>);

  const activity = screen.getByRole("region", { name: "实时活动" });
  expect(within(activity).getByText("正在同步并下载")).toBeVisible();
  expect(within(activity).getAllByText("喜欢").length).toBeGreaterThanOrEqual(1);
  expect(within(activity).getByText("已发现 9 · 新增任务 4")).toBeVisible();
  expect(within(activity).getByText("海边日落")).toBeVisible();
  expect(within(activity).getByText("旅行家 · 想去的地方")).toBeVisible();
  expect(within(activity).getByText("25 B / 100 B")).toBeVisible();
  expect(within(activity).getByText("10 B/s")).toBeVisible();
  expect(within(activity).getByRole("progressbar", { name: "海边日落 下载进度" })).toHaveAttribute("aria-valuenow", "25");
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

it("keeps source copy outside the fixed-size icon well", () => {
  render(<ThemeProvider><HomePage onOpenDownloads={vi.fn()} onOpenSource={vi.fn()} /></ThemeProvider>);

  const source = screen
    .getByRole("region", { name: "收藏分类进度" })
    .querySelector<HTMLButtonElement>(".home-source-identity");
  expect(source).toBeTruthy();
  if (!source) throw new Error("missing source identity button");
  expect(source.querySelectorAll(":scope > .app-icon-well")).toHaveLength(1);
  const copy = source.querySelector(".home-source-copy");
  expect(copy).toBeTruthy();
  expect(copy).toContainElement(screen.getByText("想去的地方"));
});

it("shows category archive progress against the remote total when it is known", () => {
  render(<ThemeProvider><HomePage onOpenDownloads={vi.fn()} onOpenSource={vi.fn()} /></ThemeProvider>);

  const region = screen.getByRole("region", { name: "收藏分类进度" });
  expect(within(region).getByText("84 / 150 已归档")).toBeVisible();
  expect(within(region).getByRole("progressbar", { name: "想去的地方 收藏分类进度" })).toHaveAttribute("aria-valuenow", "56");
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
