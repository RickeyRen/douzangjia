import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { resetArchiveProgress } from "../lib/useArchiveProgress";
import { WithAppData } from "../test/appData";
import { makeHealth, makeItem } from "../test/fixtures";
import { makeAppData } from "../test/makeAppData";
import { heatmapGrid, savingStreak, speedSeries } from "./homeChartData";
import { HomePage } from "./HomePage";

vi.mock("../app/api", async (original) => ({
  ...(await original<typeof api>()),
  fetchHome: vi.fn(),
  fetchMissingSummary: vi.fn(),
  fetchArchiveProgress: vi.fn(),
}));

function days(counts: number[]) {
  const end = Date.UTC(2026, 10, 8);
  return counts.map((count, index) => ({
    date: new Date(end - (counts.length - 1 - index) * 86_400_000).toISOString().slice(0, 10),
    count,
  }));
}

beforeEach(() => {
  vi.clearAllMocks();
  resetArchiveProgress();
  vi.mocked(api.fetchHome).mockResolvedValue({
    stats: { items: 18402, videos: 14246, galleries: 4156, downloadedItems: 4695, archivedBytes: 88_046_829_568, creators: 13229, starred: 0, gone: 0, remoteChecked: 0, vanishedCreators: 14 },
    vanishedCreators: [{ id: "c1", nickname: "是小周ya", uniqueId: null, avatarUrl: null, status: "banned", since: 1, itemCount: 37 }],
    activity: { dailySaved: days(Array.from({ length: 70 }, (_, index) => index % 3)), speed: [], speedBucketSeconds: 600, week: { items: 128, saved: 312, creators: 41, vanished: 2 } },
    health: makeHealth(),
    recent: [makeItem()],
    starred: [],
    gone: [],
    shelves: [],
    creators: [],
  });
  vi.mocked(api.fetchMissingSummary).mockResolvedValue({ missing: 13900, queued: 8, estimatedBytes: null });
  vi.mocked(api.fetchArchiveProgress).mockResolvedValue({
    active: {
      status: "running",
      batches: [{ id: 1, kind: "missing", label: "全部保存", status: "running", totalItems: 13892, completedCount: 1203, failedCount: 0, createdAt: 1 }],
      totalItems: 13892,
      completedItems: 1203,
      failedItems: 0,
      runningItems: 3,
      waitingItems: 12686,
      downloadedBytes: 1,
      estimatedTotalBytes: null,
      speedBps: 13_000_000,
      itemsPerMinute: 11,
      etaSeconds: 72_000,
      startedAt: 1,
      current: [],
    },
    failures: [{ remoteId: "9", description: "坏掉的", author: "x", coverUrl: null, errorCode: "MEDIA_URL_UNAVAILABLE", attempts: 5, failedAt: 1 }],
    failedTotal: 5,
  });
});
afterEach(cleanup);

it("shows the progress, failure and save-everything cards together", async () => {
  render(
    <WithAppData value={makeAppData({ health: makeHealth() })}>
      <HomePage />
    </WithAppData>,
  );

  expect(await screen.findByRole("region", { name: "下载进度" })).toHaveTextContent("1,203");
  expect(await screen.findByText("5 个作品没能存到 NAS")).toBeInTheDocument();
  expect(screen.getByText(/暂时拿不到新的下载链接/)).toBeInTheDocument();
  // Only the items no download is waiting on are offered.
  expect(screen.getByText("13,892")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /全部存到 NAS/ })).toBeInTheDocument();
  expect(screen.getByText("+128")).toBeInTheDocument();
  expect(screen.getByText("是小周ya")).toBeInTheDocument();
  expect(screen.getByText("已封禁")).toBeInTheDocument();
});

it("lays out ten weeks ending with today's week", () => {
  // 2026-11-08 is a Sunday, so the last column is complete.
  const grid = heatmapGrid(days([...Array(69).fill(0), 8]));
  expect(grid.columns).toHaveLength(10);
  expect(grid.columns[9].cells[6]).toMatchObject({ date: "2026-11-08", count: 8, level: 4 });
  expect(grid.max).toBe(8);

  // A Wednesday leaves the rest of the week as future cells.
  const midweek = heatmapGrid(days([...Array(69).fill(1), 2]).map((day) => ({ ...day, date: shift(day.date, -4) })));
  expect(midweek.columns[9].cells[2]).toMatchObject({ date: "2026-11-04", future: false });
  expect(midweek.columns[9].cells[3]).toMatchObject({ future: true });
});

function shift(date: string, by: number) {
  return new Date(Date.parse(date) + by * 86_400_000).toISOString().slice(0, 10);
}

it("counts the saving streak back from today or yesterday", () => {
  expect(savingStreak(days([0, 3, 2, 5]))).toBe(3);
  expect(savingStreak(days([1, 3, 2, 0]))).toBe(3);
  expect(savingStreak(days([1, 0, 2, 0]))).toBe(1);
  expect(savingStreak(days([0, 0]))).toBe(0);
});

it("fills quiet buckets with zero across the last day", () => {
  const now = 1_800_000_000;
  const end = Math.floor(now / 600) * 600;
  const series = speedSeries([{ at: end, bps: 100 }], 600, now);
  expect(series).toHaveLength(144);
  expect(series[143]).toEqual({ at: end, bps: 100 });
  expect(series[0].bps).toBe(0);
});
