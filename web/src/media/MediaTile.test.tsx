import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { makeItem } from "../test/fixtures";
import { MediaTile } from "./MediaTile";

afterEach(cleanup);

it("falls back from the local poster to the Douyin cover, then to text", () => {
  const item = makeItem({ thumbnailUrl: "/api/media/1/poster", coverUrl: "https://cdn.invalid/cover.jpg", description: "海边的日落", media: [] });
  const { container } = render(<MediaTile item={item} onOpen={vi.fn()} />);

  const image = () => container.querySelector(".tile-media img");
  expect(image()).toHaveAttribute("src", "/api/media/1/poster");
  fireEvent.error(image()!);
  expect(image()).toHaveAttribute("src", "https://cdn.invalid/cover.jpg");
  fireEvent.error(image()!);
  expect(image()).toBeNull();
  expect(screen.getAllByText("海边的日落").length).toBeGreaterThan(0);
});

it("marks stars, galleries and items still in the cloud", () => {
  const item = makeItem({
    starred: true,
    type: "gallery",
    media: [],
    local: { state: "waiting", readyAssets: 0, totalAssets: 4, downloadedBytes: 0, totalBytes: null },
  });
  render(<MediaTile item={item} onOpen={vi.fn()} />);

  expect(screen.getByTitle("精选")).toBeInTheDocument();
  expect(screen.getByTitle("尚未下载到 NAS")).toBeInTheDocument();
  expect(screen.getByText("4")).toBeInTheDocument();
});

it("opens the creator from the caption", () => {
  const onOpenCreator = vi.fn();
  render(<MediaTile item={makeItem()} onOpen={vi.fn()} onOpenCreator={onOpenCreator} />);

  fireEvent.click(screen.getByRole("button", { name: "小鹿" }));

  expect(onOpenCreator).toHaveBeenCalledWith("c1", "小鹿");
});

it("flags items that are gone from Douyin", () => {
  const item = makeItem({ remoteAvailability: { status: "deleted", checkedAt: 1, evidenceCode: "ITEM_NOT_FOUND", lastAvailableAt: null } });
  render(<MediaTile item={item} onOpen={vi.fn()} />);

  expect(screen.getByTitle("抖音上已消失")).toBeInTheDocument();
});
