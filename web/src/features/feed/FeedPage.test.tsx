import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { FeedPage, feedIndexFromTarget } from "./FeedPage";

vi.mock("../../app/api", () => ({
  fetchCollections: vi.fn(),
  fetchFeed: vi.fn(),
}));

const collections = [
  { id: "1001", name: "想去的地方", itemCount: 1, lastSeenAt: 1 },
  { id: "1002", name: "好看的美女", itemCount: 1, lastSeenAt: 1 },
];

const itemFor = (collection: (typeof collections)[number]) => ({
  awemeId: collection.id,
  author: "旅行家",
  description: `来自 ${collection.name}`,
  type: "video" as const,
  publishedAt: null,
  archivedAt: 1,
  collections: [{ id: collection.id, name: collection.name }],
  media: [
    {
      id: Number(collection.id),
      index: 0,
      type: "video",
      byteSize: 10,
      mimeType: "video/mp4",
      url: `/api/media/${collection.id}`,
    },
  ],
});

describe("FeedPage", () => {
  beforeEach(() => {
    vi.mocked(api.fetchCollections).mockResolvedValue({ items: collections });
    vi.mocked(api.fetchFeed).mockImplementation(async ({ collectionId }) => ({
      items: [itemFor(collections.find((item) => item.id === collectionId) ?? collections[0])],
      nextCursor: null,
    }));
  });

  it("switches collection and keeps exactly one active media card", async () => {
    const user = userEvent.setup();
    render(<FeedPage />);

    await user.click(await screen.findByRole("button", { name: /好看的美女/ }));

    expect(await screen.findByText("来自 好看的美女")).toBeVisible();
    await waitFor(() => {
      expect(screen.getAllByTestId("feed-card-active")).toHaveLength(1);
    });
  });

  it("renders a useful empty state instead of a blank viewport", async () => {
    vi.mocked(api.fetchFeed).mockResolvedValue({ items: [], nextCursor: null });
    render(<FeedPage />);
    expect(await screen.findByText("还没有归档作品")).toBeVisible();
  });

  it("reads the active index from the data-feed-index attribute", () => {
    const target = document.createElement("div");
    target.dataset.feedIndex = "2";
    expect(feedIndexFromTarget(target)).toBe(2);
  });
});
