import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { ArchiveStatusPanel } from "./ArchiveStatusPanel";

const snapshot = {
  summary: {
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
  items: [
    {
      id: 708,
      kind: "download",
      remoteId: "734",
      author: "旅行家",
      description: "海边日落",
      collections: ["想去的地方"],
      status: "retry",
      attempts: 8,
      nextAttemptAt: 1_800,
      errorCode: "MEDIA_HTTP_ERROR",
      updatedAt: 1_700,
      currentAssetIndex: 0,
      downloadedBytes: 15_429_894,
      totalBytes: 50_000_000,
      speedBps: 0,
      etaSeconds: null,
      assets: [
        {
          index: 0,
          fileName: "000.mp4",
          mediaType: "video",
          status: "retry",
          downloadedBytes: 15_429_894,
          totalBytes: 50_000_000,
          speedBps: 0,
          etaSeconds: null,
          updatedAt: 1_700,
        },
      ],
    },
  ],
};

vi.mock("../../app/api", () => ({
  fetchJobs: vi.fn(),
  fetchStatus: vi.fn(),
  fetchSyncRuns: vi.fn(),
  triggerSync: vi.fn(),
}));

beforeEach(() => {
  vi.setSystemTime(new Date(1_780_000));
  vi.mocked(api.fetchJobs).mockResolvedValue(snapshot);
  vi.mocked(api.fetchSyncRuns).mockResolvedValue({ items: [] });
  vi.mocked(api.fetchStatus).mockResolvedValue({ configured: true, authenticated: true, douyinAuthenticated: true });
  vi.mocked(api.triggerSync).mockResolvedValue({ runId: 41 });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.clearAllMocks();
});

it("refreshes activity while open and stops after unmount", async () => {
  vi.useFakeTimers();
  const view = render(<ArchiveStatusPanel kind="activity" onClose={vi.fn()} />);
  await act(async () => undefined);
  expect(api.fetchJobs).toHaveBeenCalledTimes(1);

  await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
  expect(api.fetchJobs).toHaveBeenCalledTimes(2);

  view.unmount();
  await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
  expect(api.fetchJobs).toHaveBeenCalledTimes(2);
});

it("switches between download and sync activity", async () => {
  const user = userEvent.setup();
  render(<ArchiveStatusPanel kind="activity" onClose={vi.fn()} />);

  const downloads = await screen.findByRole("tab", { name: "下载" });
  const sync = screen.getByRole("tab", { name: "同步" });
  expect(downloads).toHaveAttribute("aria-selected", "true");
  await user.click(sync);
  expect(sync).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("button", { name: "立即全量同步" })).toBeVisible();
});

it("shows queue progress and expands complete task and asset details", async () => {
  const user = userEvent.setup();
  render(<ArchiveStatusPanel kind="activity" onClose={vi.fn()} />);

  const queue = await screen.findByRole("region", { name: "下载队列" });
  expect(within(queue).getByText("14.7 MB / 47.7 MB")).toBeVisible();
  expect(within(queue).getByText("1.2 MB/s")).toBeVisible();
  expect(within(queue).getByText("约 28 秒")).toBeVisible();
  const task = screen.getByRole("button", { name: /海边日落/ });
  expect(task).toHaveAttribute("aria-expanded", "false");

  await user.click(task);

  expect(task).toHaveAttribute("aria-expanded", "true");
  expect(screen.getAllByText("旅行家").at(-1)).toBeVisible();
  expect(screen.getByText("想去的地方")).toBeVisible();
  expect(screen.getByText("000.mp4")).toBeVisible();
  expect(screen.getByText(/媒体服务器拒绝了下载请求/)).toBeVisible();
  expect(screen.getByText(/20 秒后重试/)).toBeVisible();
});

it("uses an indeterminate progress bar when total bytes are unknown", async () => {
  vi.mocked(api.fetchJobs).mockResolvedValue({
    summary: { ...snapshot.summary, totalBytes: null, etaSeconds: null },
    items: [
      {
        ...snapshot.items[0],
        status: "running",
        totalBytes: null,
        assets: [{ ...snapshot.items[0].assets[0], status: "running", totalBytes: null }],
      },
    ],
  });

  render(<ArchiveStatusPanel kind="downloads" onClose={vi.fn()} />);

  const queue = await screen.findByRole("region", { name: "下载队列" });
  expect(within(queue).getByText(/总大小未知/)).toBeVisible();
  const progress = within(queue).getByRole("progressbar", { name: "队列下载进度" });
  expect(progress).not.toHaveAttribute("aria-valuenow");
});
