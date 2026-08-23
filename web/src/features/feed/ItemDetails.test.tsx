import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import type { FeedItem } from "../../app/api";
import { DesktopItemDetails } from "./DesktopItemDetails";
import { ItemDetailsSheet } from "./ItemDetailsSheet";

vi.mock("../../app/api", async () => {
  const actual = await vi.importActual<typeof import("../../app/api")>("../../app/api");
  return { ...actual, checkRemoteAvailability: vi.fn() };
});

const item: FeedItem = {
  awemeId: "734",
  creatorId: "creator-1",
  author: "旅行作者",
  description: "海边日落",
  type: "video",
  publishedAt: 100,
  archivedAt: 200,
  sourceUrl: "https://www.douyin.com/video/734",
  coverUrl: null,
  creator: { id: "creator-1", nickname: "旅行作者", uniqueId: "travel", avatarUrl: null },
  douyin: {
    statistics: { playCount: 1000, diggCount: 50, commentCount: 4, collectCount: 8, shareCount: 2 },
    durationMs: 15_200,
    hashtags: ["旅行"],
    music: { title: "海风" },
    visibility: "public",
  },
  collections: [{ id: "travel", name: "想去的地方" }],
  media: [{
    id: 1,
    index: 0,
    type: "video",
    byteSize: 1234,
    mimeType: "video/mp4",
    url: "/api/media/1",
    relativePath: "objects/734/000-video.mp4",
    checksumSha256: "abc123",
    completedAt: 300,
    technical: { width: 1080, height: 1920, codec: "h264", fps: 30, bitRate: 4_500_000, durationMs: 15_200, probeStatus: "ready", probedAt: 300 },
  }],
  remoteAvailability: { status: "available", checkedAt: 200, evidenceCode: "OK", lastAvailableAt: 200 },
  local: { state: "downloaded", readyAssets: 1, totalAssets: 1, downloadedBytes: 1234, totalBytes: 1234 },
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("shows Douyin statistics, remote state, and local technical file details", () => {
  render(<DesktopItemDetails item={item} />);

  expect(screen.getByText("远端可用")).toBeVisible();
  expect(screen.getByText("1,000")).toBeVisible();
  expect(screen.getByText("1080 × 1920")).toBeVisible();
  expect(screen.getByText("h264 · 30 fps")).toBeVisible();
  expect(screen.getByText("abc123")).toBeVisible();
  expect(screen.getByText("#旅行")).toBeVisible();
});

it("shows the creator Douyin ID directly in every item details sidebar", () => {
  const { rerender } = render(<DesktopItemDetails item={item} />);

  expect(screen.getByText("抖音号")).toBeVisible();
  expect(screen.getByText("travel")).toBeVisible();

  rerender(<ItemDetailsSheet item={item} onClose={vi.fn()} />);

  expect(screen.getByText("抖音号")).toBeVisible();
  expect(screen.getByText("travel")).toBeVisible();
});

it("keeps the Douyin ID row visible when the creator identity is unavailable", () => {
  render(<DesktopItemDetails item={{ ...item, creator: null }} />);

  expect(screen.getByText("抖音号")).toBeVisible();
  expect(screen.getByText("暂未获取")).toBeVisible();
});

it("rechecks the remote item and keeps the local file visible when Douyin deleted it", async () => {
  const user = userEvent.setup();
  vi.mocked(api.checkRemoteAvailability).mockResolvedValue({
    status: "deleted",
    checkedAt: 400,
    evidenceCode: "ITEM_NOT_FOUND",
    lastAvailableAt: 200,
  });
  render(<ItemDetailsSheet item={item} onClose={vi.fn()} />);

  await user.click(screen.getByRole("button", { name: "重新检查远端状态" }));

  expect(api.checkRemoteAvailability).toHaveBeenCalledWith("734");
  expect(await screen.findByText("已从抖音删除")).toBeVisible();
  expect(screen.getByText("objects/734/000-video.mp4")).toBeVisible();
  expect(screen.getByText("已下载到 NAS")).toBeVisible();
});
