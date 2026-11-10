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

it("offers to download an item that is not on the NAS yet", async () => {
  const user = userEvent.setup();
  const { onItemPatch } = renderPlayer({ index: 2 });

  expect(screen.getByText("这个作品还没有下载到 NAS。")).toBeInTheDocument();
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
