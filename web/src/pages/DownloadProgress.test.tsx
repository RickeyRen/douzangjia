import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { WithAppData } from "../test/appData";
import { makeAppData } from "../test/makeAppData";
import { resetArchiveProgress } from "../lib/useArchiveProgress";
import { DownloadProgress } from "./DownloadProgress";

vi.mock("../app/api", async (original) => ({
  ...(await original<typeof api>()),
  controlArchiveBatch: vi.fn(),
  retryFailedDownloads: vi.fn(),
  fetchArchiveProgress: vi.fn(),
}));

const active = (values: Partial<NonNullable<api.ArchiveProgress["active"]>> = {}): api.ArchiveProgress => ({
  active: {
    status: "running",
    batches: [{ id: 7, kind: "missing", label: "全部未存作品", status: "running", totalItems: 200, completedCount: 50, failedCount: 2, createdAt: 1 }],
    totalItems: 200,
    completedItems: 50,
    failedItems: 2,
    runningItems: 2,
    waitingItems: 146,
    downloadedBytes: 1_500_000_000,
    estimatedTotalBytes: 6_000_000_000,
    speedBps: 4_000_000,
    itemsPerMinute: 6,
    etaSeconds: 1500,
    startedAt: 1,
    current: [{ remoteId: "1", description: "海边日落", author: "小鹿", coverUrl: null, downloadedBytes: 1000, totalBytes: 4000 }],
    ...values,
  },
  failures: [{ remoteId: "9", description: "坏掉的视频", author: "某人", coverUrl: null, errorCode: null, attempts: 5, failedAt: 1 }],
  failedTotal: 2,
});

beforeEach(() => {
  vi.clearAllMocks();
  resetArchiveProgress();
  vi.mocked(api.fetchArchiveProgress).mockResolvedValue(active());
});
afterEach(cleanup);

it("shows overall percent, size, speed and what is downloading now", () => {
  render(
    <WithAppData value={makeAppData()}>
      <DownloadProgress progress={active()} variant="full" />
    </WithAppData>,
  );
  expect(screen.getByText("正在存到 NAS")).toBeInTheDocument();
  expect(screen.getByText("25%")).toBeInTheDocument();
  expect(screen.getByText("已完成 50 / 200 个作品")).toBeInTheDocument();
  expect(screen.getByText("海边日落")).toBeInTheDocument();
  expect(screen.getByText("2 个作品下载失败")).toBeInTheDocument();
});

it("pauses every running batch", async () => {
  vi.mocked(api.controlArchiveBatch).mockResolvedValue({ id: 7, kind: "missing", targetId: "all", status: "paused" });
  const user = userEvent.setup();
  render(
    <WithAppData value={makeAppData()}>
      <DownloadProgress progress={active()} variant="home" />
    </WithAppData>,
  );
  await user.click(screen.getByRole("button", { name: /暂停/ }));
  expect(api.controlArchiveBatch).toHaveBeenCalledWith(7, "pause");
  expect(screen.getByText("2 个下载失败，去状态页重试")).toBeInTheDocument();
});

it("retries failed downloads when nothing else is running", async () => {
  vi.mocked(api.retryFailedDownloads).mockResolvedValue({ retried: 2 });
  const appData = makeAppData();
  const user = userEvent.setup();
  render(
    <WithAppData value={appData}>
      <DownloadProgress progress={{ ...active(), active: null }} variant="home" />
    </WithAppData>,
  );
  expect(screen.getByText("2 个作品没能存到 NAS")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /全部重试/ }));
  await waitFor(() => expect(appData.toast).toHaveBeenCalledWith("已重新加入 2 个作品"));
});
