import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { WithAppData } from "../test/appData";
import { makeAppData } from "../test/makeAppData";
import { makeItem } from "../test/fixtures";
import { Player, type PlayerProps } from "./Player";

vi.mock("../app/api", async (original) => ({
  ...(await original<typeof api>()),
  archiveItem: vi.fn(async () => ({ id: 1, kind: "item", targetId: "x", status: "queued" })),
  checkRemoteAvailability: vi.fn(),
  fetchItem: vi.fn(),
}));

const items = [
  makeItem({ awemeId: "7000000000000000101" }),
  makeItem({
    awemeId: "7000000000000000102",
    type: "gallery",
    media: [0, 1, 2].map((index) => ({ id: 200 + index, index, type: "image", byteSize: 10, mimeType: "image/webp", url: `/api/media/${200 + index}`, posterUrl: `/api/media/${200 + index}/poster` })),
    local: { state: "downloaded", readyAssets: 3, totalAssets: 3, downloadedBytes: 30, totalBytes: 30 },
  }),
  makeItem({ awemeId: "7000000000000000103", media: [], local: { state: "waiting", readyAssets: 0, totalAssets: 1, downloadedBytes: 0, totalBytes: null } }),
];

function renderPlayer(props: Partial<PlayerProps> = {}, appData = makeAppData()) {
  const handlers = { onIndexChange: vi.fn(), onClose: vi.fn(), onItemPatch: vi.fn(), onLoadMore: vi.fn() };
  render(
    <WithAppData value={appData}>
      <Player items={items} index={0} {...handlers} {...props} />
    </WithAppData>,
  );
  return { ...handlers, appData };
}

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
});
afterEach(cleanup);

/** jsdom never runs CSS transitions; finish the slide the way the browser would. */
function settle() {
  const track = document.querySelector(".player-track");
  if (track) fireEvent.transitionEnd(track);
}

it("moves between items with the arrow keys and closes on Escape", () => {
  const { onIndexChange, onClose } = renderPlayer();

  fireEvent.keyDown(window, { key: "ArrowDown" });
  settle();
  fireEvent.keyDown(window, { key: "ArrowUp" });
  settle();
  fireEvent.keyDown(window, { key: "Escape" });

  expect(onIndexChange).toHaveBeenCalledWith(1);
  expect(onIndexChange).toHaveBeenCalledTimes(1); // already at the first item
  expect(onClose).toHaveBeenCalledOnce();
});

it("pages through gallery images before leaving the item", () => {
  const { onIndexChange } = renderPlayer({ index: 1 });
  expect(screen.getByLabelText("第 1 张，共 3 张")).toBeInTheDocument();

  fireEvent.keyDown(window, { key: "ArrowRight" });
  fireEvent.keyDown(window, { key: "ArrowRight" });
  expect(screen.getByLabelText("第 3 张，共 3 张")).toBeInTheDocument();
  expect(onIndexChange).not.toHaveBeenCalled();

  fireEvent.keyDown(window, { key: "ArrowRight" });
  settle();
  expect(onIndexChange).toHaveBeenCalledWith(2);
});

it("slides to the next item when swiped up past a fifth of the screen", () => {
  const { onIndexChange } = renderPlayer();
  const stage = document.querySelector(".player-stage")!;
  Object.defineProperty(stage, "clientHeight", { value: 800 });

  fireEvent.touchStart(stage, { touches: [{ clientX: 200, clientY: 600 }] });
  fireEvent.touchMove(stage, { touches: [{ clientX: 202, clientY: 500 }] });
  const track = document.querySelector<HTMLElement>(".player-track")!;
  expect(track.style.transform).toBe("translate3d(0, -100px, 0)"); // follows the finger
  fireEvent.touchMove(stage, { touches: [{ clientX: 204, clientY: 380 }] });
  fireEvent.touchEnd(stage, { changedTouches: [{ clientX: 204, clientY: 380 }] });
  expect(track.style.transform).toBe("translate3d(0, -800px, 0)");
  settle();

  expect(onIndexChange).toHaveBeenCalledWith(1);
});

it("springs back on a short swipe", () => {
  const { onIndexChange } = renderPlayer();
  const stage = document.querySelector(".player-stage")!;
  Object.defineProperty(stage, "clientHeight", { value: 800 });

  fireEvent.touchStart(stage, { touches: [{ clientX: 200, clientY: 600 }] });
  fireEvent.touchMove(stage, { touches: [{ clientX: 200, clientY: 580 }] });
  fireEvent.touchEnd(stage, { changedTouches: [{ clientX: 200, clientY: 580 }] });
  settle();

  expect(onIndexChange).not.toHaveBeenCalled();
  expect(document.querySelector<HTMLElement>(".player-track")!.style.transform).toBe("translate3d(0, 0px, 0)");
});

it("loops the current video by default and buffers the next one", () => {
  renderPlayer({ items: [items[0], makeItem({ awemeId: "7000000000000000109" })] });
  const videos = document.querySelectorAll("video");
  expect(videos).toHaveLength(2);
  expect(videos[0].loop).toBe(true);
  expect(videos[1].getAttribute("preload")).toBe("auto");
  expect(videos[1].muted).toBe(true);
  expect(screen.getByRole("button", { name: "开启自动连播" })).toBeInTheDocument();
});

it("stars with S and reports the new state back to the list", async () => {
  const { onItemPatch, appData } = renderPlayer();

  fireEvent.keyDown(window, { key: "s" });

  await vi.waitFor(() => expect(onItemPatch).toHaveBeenCalledWith(items[0].awemeId, { starred: true }));
  expect(appData.toggleStar).toHaveBeenCalledWith(items[0]);
});

it("asks for the next page before reaching the end", () => {
  const { onLoadMore } = renderPlayer({ index: 1, hasMore: true });
  expect(onLoadMore).toHaveBeenCalled();
});

it("plays an item that is not on the NAS yet from Douyin and saves it", async () => {
  const failed = makeItem({ awemeId: "7000000000000000104", media: [], local: { state: "failed", readyAssets: 0, totalAssets: 1, downloadedBytes: 0, totalBytes: null } });
  const { onItemPatch } = renderPlayer({ items: [failed], index: 0 });

  const video = document.querySelector("video")!;
  expect(video.getAttribute("src")).toBe(`/api/items/${failed.awemeId}/stream`);
  expect(screen.getByText("从抖音播放，同时存到 NAS")).toBeInTheDocument();
  await vi.waitFor(() => expect(api.archiveItem).toHaveBeenCalledWith(failed.awemeId));
  expect(onItemPatch).toHaveBeenCalledWith(failed.awemeId, { local: { ...failed.local, state: "waiting" } });
});

it("saves a streamed work the NAS reports as waiting, which also means no download yet", async () => {
  const waiting = makeItem({ awemeId: "7000000000000000106", media: [], local: { state: "waiting", readyAssets: 0, totalAssets: 1, downloadedBytes: 0, totalBytes: null } });
  renderPlayer({ items: [waiting], index: 0 });

  await vi.waitFor(() => expect(api.archiveItem).toHaveBeenCalledWith(waiting.awemeId));
});

it("says so once a streamed work has landed on the NAS, without restarting it", async () => {
  vi.useFakeTimers();
  try {
    const waiting = makeItem({ awemeId: "7000000000000000105", media: [], local: { state: "failed", readyAssets: 0, totalAssets: 1, downloadedBytes: 0, totalBytes: null } });
    const saved = { ...waiting, local: { state: "downloaded" as const, readyAssets: 1, totalAssets: 1, downloadedBytes: 10, totalBytes: 10 }, media: [{ id: 9, index: 0, type: "video" as const, byteSize: 10, mimeType: "video/mp4", url: "/api/media/9", posterUrl: "/api/media/9/poster" }] };
    vi.mocked(api.fetchItem).mockResolvedValue(saved);
    const handlers = { onIndexChange: vi.fn(), onClose: vi.fn(), onLoadMore: vi.fn() };
    const { rerender } = render(<WithAppData value={makeAppData()}><Player items={[waiting]} index={0} {...handlers} onItemPatch={vi.fn()} /></WithAppData>);
    await vi.advanceTimersByTimeAsync(5100);
    expect(api.fetchItem).toHaveBeenCalledWith(waiting.awemeId);
    rerender(<WithAppData value={makeAppData()}><Player items={[saved]} index={0} {...handlers} onItemPatch={vi.fn()} /></WithAppData>);
    expect(screen.getByText("已存到 NAS，下次直接从 NAS 播放")).toBeInTheDocument();
    expect(document.querySelector("video")!.getAttribute("src")).toBe(`/api/items/${waiting.awemeId}/stream`);
  } finally {
    vi.useRealTimers();
  }
});

it("falls back to the download offer when Douyin will not hand the video over", async () => {
  const user = userEvent.setup();
  const { onItemPatch } = renderPlayer({ index: 2 });

  fireEvent.error(document.querySelector(".player-slide[aria-hidden='false'] video")!);

  expect(await screen.findByText("这个作品还没有下载到 NAS。")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "立即下载" }));
  expect(api.archiveItem).toHaveBeenCalledWith(items[2].awemeId);
  expect(onItemPatch).toHaveBeenCalledWith(items[2].awemeId, { local: { ...items[2].local, state: "waiting" } });
});

it("ignores shortcuts while typing in a field", () => {
  const { onIndexChange } = renderPlayer();
  const input = document.createElement("input");
  document.body.appendChild(input);

  fireEvent.keyDown(input, { key: "ArrowDown" });

  expect(onIndexChange).not.toHaveBeenCalled();
  input.remove();
});

it("moves one item per scroll gesture, however many wheel events it fires", () => {
  const { onIndexChange } = renderPlayer();
  const stage = document.querySelector(".player-stage")!;
  for (let step = 0; step < 12; step += 1) fireEvent.wheel(stage, { deltaY: 80 });
  settle();
  expect(onIndexChange).toHaveBeenCalledTimes(1);
  expect(onIndexChange).toHaveBeenCalledWith(1);
});

it("jumps 10 seconds inside a video with Shift+arrows instead of changing works", () => {
  const { onIndexChange } = renderPlayer();
  const video = document.querySelector("video")!;
  Object.defineProperty(video, "duration", { value: 300, configurable: true });
  video.currentTime = 60;

  fireEvent.keyDown(window, { key: "ArrowRight", shiftKey: true });
  expect(video.currentTime).toBe(70);
  fireEvent.keyDown(window, { key: "ArrowLeft", shiftKey: true });
  fireEvent.keyDown(window, { key: "ArrowLeft", shiftKey: true });
  expect(video.currentTime).toBe(50);
  video.currentTime = 5;
  fireEvent.keyDown(window, { key: "ArrowLeft", shiftKey: true });
  expect(video.currentTime).toBe(0);
  expect(onIndexChange).not.toHaveBeenCalled();
});

it("lays the page out like Douyin: counts on the rail, tags and sound in the caption", () => {
  const item = makeItem({
    awemeId: "7000000000000000120",
    description: "春天的海边 #旅行 #vlog",
    douyin: { statistics: { diggCount: 12345, commentCount: 264, collectCount: 0, shareCount: 3 }, durationMs: 10000, hashtags: ["旅行", "vlog"], music: { title: "海风", author: "某歌手" } },
  } as never);
  renderPlayer({ items: [item] });

  expect(screen.getByRole("button", { name: "加入精选" })).toHaveTextContent("1.2万");
  expect(screen.getByRole("img", { name: "评论没有存档" })).toHaveTextContent("264");
  expect(screen.getByRole("button", { name: "收藏与整理" })).toHaveTextContent("收藏");
  expect(screen.getByText("#旅行").tagName).toBe("STRONG");
  expect(screen.getByText("海风 - 某歌手")).toBeInTheDocument();
});

it("stars on a double tap but never unstars, and a single tap waits to tell them apart", async () => {
  vi.useFakeTimers();
  try {
    const { appData } = renderPlayer();
    const video = document.querySelector(".player-slide[aria-hidden='false'] video")!;
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);

    fireEvent.click(video);
    fireEvent.click(video);
    await vi.advanceTimersByTimeAsync(400);

    expect(appData.toggleStar).toHaveBeenCalledTimes(1);
    expect(document.querySelector(".heart-burst")).not.toBeNull();
    pause.mockRestore();
  } finally {
    vi.useRealTimers();
  }
});

it("shows the cover until the first frame and does not buffer a neighbour still on Douyin", () => {
  const streamed = makeItem({ awemeId: "7000000000000000121", media: [], local: { state: "failed", readyAssets: 0, totalAssets: 1, downloadedBytes: 0, totalBytes: null } });
  renderPlayer({ items: [items[0], streamed] });

  const [current, next] = document.querySelectorAll("video");
  expect(next.getAttribute("preload")).toBe("none");
  const cover = () => document.querySelector(".player-slide[aria-hidden='false'] .player-cover");
  expect(cover()).not.toBeNull();
  fireEvent.loadedData(current);
  expect(cover()).toBeNull();
});
