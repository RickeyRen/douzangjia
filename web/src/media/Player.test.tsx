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

it("moves between items with the arrow keys and closes on Escape", () => {
  const { onIndexChange, onClose } = renderPlayer();

  fireEvent.keyDown(window, { key: "ArrowDown" });
  fireEvent.keyDown(window, { key: "ArrowUp" });
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
  expect(onIndexChange).toHaveBeenCalledWith(2);
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
