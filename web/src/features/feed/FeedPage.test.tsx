import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { FeedPage, feedIndexFromTarget } from "./FeedPage";

vi.mock("../../app/api", () => ({
  fetchCollections: vi.fn(),
  fetchFeed: vi.fn(),
  fetchJobs: vi.fn(),
  fetchStatus: vi.fn(),
  fetchSyncRuns: vi.fn(),
  triggerSync: vi.fn(),
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
    vi.mocked(api.fetchJobs).mockResolvedValue({
      items: [
        {
          id: 1,
          kind: "download",
          remoteId: "734",
          status: "completed",
          attempts: 1,
          nextAttemptAt: 1,
          errorCode: null,
          updatedAt: 1,
        },
      ],
    });
    vi.mocked(api.fetchSyncRuns).mockResolvedValue({
      items: [
        {
          id: 9,
          mode: "full",
          phase: "finished",
          status: "completed",
          discovered: 12,
          enqueued: 10,
          errorCode: null,
          startedAt: 1,
          finishedAt: 2,
        },
      ],
    });
    vi.mocked(api.fetchStatus).mockResolvedValue({
      configured: true,
      authenticated: true,
      douyinAuthenticated: true,
    });
    vi.mocked(api.triggerSync).mockResolvedValue({ runId: 10 });
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

  it("opens real download, sync, and settings panels", async () => {
    const user = userEvent.setup();
    const view = within(render(<FeedPage />).container);

    await user.click(await view.findByRole("button", { name: "下载任务" }));
    expect(await view.findByText("作品 734")).toBeVisible();
    await user.click(view.getByRole("button", { name: "关闭面板" }));

    await user.click(view.getByRole("button", { name: "同步状态" }));
    expect(await view.findByText("发现 12 · 新增 10")).toBeVisible();
    await user.click(view.getByRole("button", { name: "立即全量同步" }));
    expect(await view.findByText("全量同步 #10 已进入队列")).toBeVisible();
    await user.click(view.getByRole("button", { name: "关闭面板" }));

    await user.click(view.getByRole("button", { name: "设置" }));
    expect(await view.findByText("抖音已连接")).toBeVisible();
    expect(view.getByText("永久保留本地原文件")).toBeVisible();
  });
});
