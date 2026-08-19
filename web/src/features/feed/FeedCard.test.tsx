import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import type { FeedItem } from "../../app/api";
import { FeedCard } from "./FeedCard";

const item: FeedItem = {
  awemeId: "7384162057",
  creatorId: "creator-1",
  author: "旅行家",
  description: "海边日落",
  type: "video",
  publishedAt: 1,
  archivedAt: 2,
  sourceUrl: "https://www.douyin.com/video/7384162057",
  collections: [{ id: "1001", name: "想去的地方" }],
  media: [{ id: 91, index: 0, type: "video", byteSize: 1024, mimeType: "video/mp4", url: "/api/media/91" }],
  local: { state: "downloaded", readyAssets: 1, totalAssets: 1, downloadedBytes: 1024, totalBytes: 1024 },
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("pauses, resumes, unmutes, and opens details with touch controls", async () => {
  const user = userEvent.setup();
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  const onOpenDetails = vi.fn();
  const view = render(<FeedCard item={item} active onOpenDetails={onOpenDetails} />);

  expect(view.container.querySelector("[data-testid='feed-card-active']")).toHaveClass(
    "archive-media-stage",
  );
  expect(view.container.querySelector(".archive-media-frame")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "暂停视频" }));
  expect(pause).toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "播放视频" }));
  expect(play).toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "打开声音" }));
  expect(screen.getByRole("button", { name: "静音" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "作品信息" }));
  expect(onOpenDetails).toHaveBeenCalledWith(item);
});

it("does not expose a dead sound control for image galleries", () => {
  const gallery: FeedItem = {
    ...item,
    type: "gallery",
    media: [{ ...item.media[0], type: "image", mimeType: "image/jpeg" }],
  };

  render(<FeedCard item={gallery} active />);

  expect(screen.queryByRole("button", { name: "打开声音" })).not.toBeInTheDocument();
});

it("exposes post controls as a labelled toolbar", () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  render(<FeedCard item={item} active />);

  const controls = screen.getByRole("toolbar", { name: "作品操作" });
  expect(controls).toBeVisible();
  expect(controls).toContainElement(screen.getByRole("button", { name: "打开声音" }));
  expect(controls).toContainElement(screen.getByRole("button", { name: "查看收藏夹" }));
  expect(controls).toContainElement(screen.getByRole("button", { name: "作品信息" }));
});

it("labels the post with its visible title", () => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  render(<FeedCard item={item} active />);

  expect(screen.getByRole("article", { name: "海边日落" })).toBeVisible();
});

it("opens the creator archive and shows the local download state", async () => {
  const user = userEvent.setup();
  const onOpenAuthor = vi.fn();
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  render(<FeedCard item={item} active onOpenAuthor={onOpenAuthor} />);

  await user.click(screen.getByRole("button", { name: "查看旅行家的已收藏作品" }));

  expect(onOpenAuthor).toHaveBeenCalledWith("creator-1", "旅行家");
  expect(screen.getByText("已下载到 NAS")).toBeVisible();
});

it("can request an idempotent archive batch for one post", async () => {
  const user = userEvent.setup();
  const onArchiveItem = vi.fn();
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  render(<FeedCard item={item} active onArchiveItem={onArchiveItem} />);

  await user.click(screen.getByRole("button", { name: "保存到 NAS" }));

  expect(onArchiveItem).toHaveBeenCalledWith(item);
});
