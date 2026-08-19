import { act, cleanup, render as renderView, screen, waitFor, within } from "@testing-library/react";
import type { ReactElement } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { ThemeProvider } from "../../theme/ThemeProvider";
import { FeedPage, feedIndexFromTarget, shouldAutoPaginate } from "./FeedPage";

vi.mock("../../app/api", () => ({
  fetchDashboard: vi.fn(),
  fetchArchiveBatches: vi.fn(),
  controlArchiveBatch: vi.fn(),
  fetchLibrarySources: vi.fn(),
  fetchFeed: vi.fn(),
  fetchSourceEntities: vi.fn(),
  fetchJobs: vi.fn(),
  fetchStatus: vi.fn(),
  fetchSyncRuns: vi.fn(),
  triggerSync: vi.fn(),
  fetchCreator: vi.fn(),
  archiveItem: vi.fn(),
  archiveCreator: vi.fn(),
  archiveSource: vi.fn(),
  updateCreatorSubscription: vi.fn(),
}));

const collections = [
  { id: "1001", name: "想去的地方", itemCount: 1, lastSeenAt: 1 },
  { id: "1002", name: "好看的美女", itemCount: 1, lastSeenAt: 1 },
];

const sources: api.LibrarySource[] = [
  {
    id: "account:posts", kind: "post", remoteId: "self", name: "作品",
    declaredCount: null, discoveredCount: 3, archivedCount: 1, missingCount: 0,
    syncStatus: "incomplete", complete: false, lastFullScanAt: 1,
    lastIncrementalScanAt: null, errorCode: "COUNT_UNKNOWN",
  },
  {
    id: "account:favorite_music", kind: "favorite_music", remoteId: "self", name: "收藏音乐",
    declaredCount: null, discoveredCount: 1, archivedCount: 0, missingCount: 0,
    syncStatus: "incomplete", complete: false, lastFullScanAt: 1,
    lastIncrementalScanAt: null, errorCode: "COUNT_UNKNOWN",
  },
  ...collections.map((collection) => ({
    id: `favorite_collection:${collection.id}`, kind: "favorite_collection" as const,
    remoteId: collection.id, name: collection.name, declaredCount: collection.itemCount,
    discoveredCount: collection.itemCount, archivedCount: collection.itemCount,
    missingCount: 0, syncStatus: "complete" as const, complete: true,
    lastFullScanAt: 1, lastIncrementalScanAt: null, errorCode: null,
  })),
];

const itemFor = (collection: (typeof collections)[number]) => ({
  awemeId: collection.id,
  creatorId: "creator-1",
  author: "旅行家",
  description: `来自 ${collection.name}`,
  type: "video" as const,
  publishedAt: null,
  archivedAt: 1,
  sourceUrl: `https://www.douyin.com/video/${collection.id}`,
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
  local: { state: "downloaded" as const, readyAssets: 1, totalAssets: 1, downloadedBytes: 10, totalBytes: 10 },
});

function render(ui: ReactElement) {
  return renderView(<ThemeProvider>{ui}</ThemeProvider>);
}

describe("FeedPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.mocked(api.fetchLibrarySources).mockResolvedValue({ items: sources });
    vi.mocked(api.fetchFeed).mockImplementation(async ({ sourceId }) => ({
      items: [itemFor(collections.find((item) => `favorite_collection:${item.id}` === sourceId) ?? collections[0])],
      nextCursor: null,
    }));
    vi.mocked(api.fetchSourceEntities).mockResolvedValue({
      items: [{
        id: "music:one", type: "music", title: "收藏音乐条目", subtitle: "创作者",
        coverUrl: "https://media.test/music.jpg", sourceUrl: null,
        metadata: { duration: "00:15" },
      }],
      nextCursor: null,
    });
    vi.mocked(api.fetchJobs).mockResolvedValue({
      summary: {
        pending: 0,
        running: 0,
        retry: 0,
        failed: 0,
        completed: 1,
        downloadedBytes: 0,
        totalBytes: 0,
        speedBps: 0,
        etaSeconds: 0,
      },
      items: [
        {
          id: 1,
          kind: "download",
          remoteId: "734",
          author: "",
          description: "",
          collections: [],
          status: "completed",
          attempts: 1,
          nextAttemptAt: 1,
          errorCode: null,
          updatedAt: 1,
          currentAssetIndex: null,
          downloadedBytes: 0,
          totalBytes: 0,
          speedBps: 0,
          etaSeconds: 0,
          assets: [],
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
    vi.mocked(api.fetchCreator).mockResolvedValue({
      id: "creator-1",
      nickname: "旅行家",
      uniqueId: "travel-id",
      avatarUrl: null,
      followerCount: 321,
      postCount: 17,
      knownItemCount: 1,
      archivedItemCount: 1,
      lastSeenAt: 1,
      subscription: null,
    });
    vi.mocked(api.archiveItem).mockResolvedValue({ id: 1, kind: "item", targetId: "1001", status: "completed" });
    vi.mocked(api.archiveCreator).mockResolvedValue({ id: 2, kind: "creator", targetId: "creator-1", status: "running" });
    vi.mocked(api.archiveSource).mockResolvedValue({ id: 3, kind: "source", targetId: "favorite_collection:1002", status: "running" });
    vi.mocked(api.updateCreatorSubscription).mockResolvedValue({
      creatorId: "creator-1", enabled: true, scanIntervalSeconds: 21600,
      archiveNewItems: true, lastScanAt: null, nextScanAt: 1, lastErrorCode: null,
    });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
    vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("switches collection and keeps exactly one active media card", async () => {
    const user = userEvent.setup();
    render(<FeedPage />);

    await user.click(await screen.findByRole("button", { name: /好看的美女/ }));

    await waitFor(() => {
      expect(screen.getAllByTestId("feed-card-active")).toHaveLength(1);
      expect(
        within(screen.getByTestId("feed-card-active")).getByText(
          "来自 好看的美女",
        ),
      ).toBeVisible();
    });
  });

  it("archives the entire selected collection from the top bar", async () => {
    const user = userEvent.setup();
    render(<FeedPage />);

    await user.click(await screen.findByRole("button", { name: /好看的美女/ }));
    await user.click(screen.getByRole("button", { name: "保存当前来源全部作品" }));

    expect(api.archiveSource).toHaveBeenCalledWith("favorite_collection:1002");
  });

  it("opens logged-in account sources through the unified library feed", async () => {
    const user = userEvent.setup();
    render(<FeedPage />);

    const rail = within((await screen.findByRole("navigation", { name: "打开收藏夹" })).closest("aside")!);
    await user.click(rail.getByRole("button", { name: "作品3" }));

    await waitFor(() => expect(api.fetchFeed).toHaveBeenLastCalledWith(
      expect.objectContaining({ sourceId: "account:posts" }),
    ));
  });

  it("renders favorite music as a browsable non-video library", async () => {
    const user = userEvent.setup();
    render(<FeedPage />);

    const rail = within((await screen.findByRole("navigation", { name: "打开收藏夹" })).closest("aside")!);
    await user.click(rail.getByRole("button", { name: "收藏音乐1" }));

    await waitFor(() => expect(api.fetchSourceEntities).toHaveBeenCalledWith(
      expect.objectContaining({ sourceId: "account:favorite_music" }),
    ));
    expect(await screen.findByText("收藏音乐条目")).toBeVisible();
    expect(api.fetchFeed).not.toHaveBeenLastCalledWith(
      expect.objectContaining({ sourceId: "account:favorite_music" }),
    );
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

  it("only auto-paginates while the active card is near the loaded tail", () => {
    expect(shouldAutoPaginate(18, 20)).toBe(true);
    expect(shouldAutoPaginate(19, 40)).toBe(false);
  });

  it("keeps desktop navigation, media, and details in one flow grid", async () => {
    render(<FeedPage />);

    const workspace = await screen.findByTestId("desktop-workspace");
    const content = screen.getByTestId("desktop-content");
    const details = await screen.findByTestId("desktop-details");

    expect(workspace).toHaveClass("archive-desktop-grid");
    expect(content).toBeVisible();
    expect(details).toBeVisible();
    expect(details).not.toHaveClass("absolute");
    expect(details).toHaveTextContent("旅行家");
    expect(details).toHaveTextContent("来自 想去的地方");
    expect(screen.getByRole("button", { name: "切换到亮色主题" })).toBeVisible();
  });

  it("opens real download, sync, and settings panels", async () => {
    const user = userEvent.setup();
    const view = within(render(<FeedPage />).container);
    const desktopRail = within(view.getByRole("navigation", { name: "打开收藏夹" }).closest("aside")!);

    await user.click(await desktopRail.findByRole("button", { name: "下载任务" }));
    expect(await view.findByText("作品 734")).toBeVisible();
    await user.click(view.getByRole("button", { name: "关闭面板" }));

    await user.click(desktopRail.getByRole("button", { name: "同步状态" }));
    expect(await view.findByText("发现 12 · 新增 10")).toBeVisible();
    await user.click(view.getByRole("button", { name: "立即全量同步" }));
    expect(await view.findByText("全量同步 #10 已进入队列")).toBeVisible();
    await user.click(view.getByRole("button", { name: "关闭面板" }));

    await user.click(desktopRail.getByRole("button", { name: "设置" }));
    const settingsDialog = await view.findByRole("dialog", { name: "设置" });
    expect(within(settingsDialog).getByText("抖音已连接")).toBeVisible();
    expect(within(settingsDialog).getByText("永久保留本地原文件")).toBeVisible();
  });

  it("keeps collections, search, activity, and settings reachable on mobile", async () => {
    const user = userEvent.setup();
    render(<FeedPage />);

    const navigation = await screen.findByRole("navigation", { name: "移动导航" });
    expect(within(navigation).getByRole("button", { name: "收藏夹" })).toBeVisible();
    expect(within(navigation).getByRole("button", { name: "搜索" })).toBeVisible();

    await user.click(within(navigation).getByRole("button", { name: "收藏夹" }));
    expect(screen.getByRole("dialog", { name: "切换收藏夹" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "关闭收藏夹" }));

    await user.click(within(navigation).getByRole("button", { name: "活动" }));
    expect(await screen.findByRole("dialog", { name: "控制台" })).toBeVisible();
    await user.click(screen.getByRole("button", { name: "关闭面板" }));

    await user.click(within(navigation).getByRole("button", { name: "设置" }));
    expect(await screen.findByRole("dialog", { name: "设置" })).toBeVisible();
  });

  it("shows a retry action only after background pagination fails", async () => {
    const observers: Array<{ callback: IntersectionObserverCallback; elements: Element[]; instance: IntersectionObserver }> = [];
    class FakeIntersectionObserver {
      readonly root = null;
      readonly rootMargin = "0px";
      readonly thresholds = [0];
      readonly elements: Element[] = [];
      constructor(readonly callback: IntersectionObserverCallback) {
        observers.push({ callback, elements: this.elements, instance: this as unknown as IntersectionObserver });
      }
      observe = (element: Element) => { this.elements.push(element); };
      disconnect = vi.fn();
      unobserve = vi.fn();
      takeRecords = () => [];
    }
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
    vi.mocked(api.fetchFeed)
      .mockResolvedValueOnce({ items: [itemFor(collections[0])], nextCursor: "page-2" })
      .mockRejectedValueOnce(new Error("temporary failure"))
      .mockResolvedValueOnce({ items: [itemFor(collections[1])], nextCursor: null });
    const user = userEvent.setup();
    const view = render(<FeedPage />);

    await screen.findAllByText("来自 想去的地方");
    expect(screen.queryByRole("button", { name: "加载更多" })).not.toBeInTheDocument();
    const sentinel = view.container.querySelector(".pagination-sentinel");
    expect(sentinel).not.toBeNull();
    await waitFor(() => expect(observers.some((observer) => observer.elements.includes(sentinel!))).toBe(true));
    const paginationObserver = observers.find((observer) => observer.elements.includes(sentinel!))!;
    act(() => {
      paginationObserver.callback([{ isIntersecting: true, intersectionRatio: 1, target: sentinel } as unknown as IntersectionObserverEntry], paginationObserver.instance);
    });

    await user.click(await screen.findByRole("button", { name: "加载失败，重试" }));

    await waitFor(() => expect(view.container.querySelectorAll("[data-feed-index]")).toHaveLength(2));
    expect(api.fetchFeed).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: "page-2" }));
  });

  it("opens a labelled mobile search and applies then clears its query", async () => {
    const user = userEvent.setup();
    render(<FeedPage />);
    const navigation = await screen.findByRole("navigation", { name: "移动导航" });

    await user.click(within(navigation).getByRole("button", { name: "搜索" }));
    const dialog = screen.getByRole("dialog", { name: "搜索归档" });
    const input = within(dialog).getByRole("searchbox", { name: "搜索归档" });
    await user.type(input, "旅行家");
    await waitFor(() => expect(api.fetchFeed).toHaveBeenLastCalledWith(expect.objectContaining({ search: "旅行家" })));
    await user.click(within(dialog).getByRole("button", { name: "清除搜索" }));
    expect(input).toHaveValue("");
  });

  it("opens a stable creator profile with archive-all and follow controls", async () => {
    const user = userEvent.setup();
    render(<FeedPage />);

    await user.click((await screen.findAllByRole("button", { name: "查看旅行家的已收藏作品" }))[0]);

    await waitFor(() => expect(api.fetchFeed).toHaveBeenLastCalledWith(expect.objectContaining({
      creatorId: "creator-1",
      sourceId: undefined,
    })));
    expect(screen.getByRole("heading", { name: "@旅行家" })).toBeVisible();
    expect(await screen.findByText("本地已归档 1 / 已发现 1")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "保存该博主全部作品" }));
    expect(api.archiveCreator).toHaveBeenCalledWith("creator-1");
    await user.click(screen.getByRole("button", { name: "开启自动追更" }));
    expect(api.updateCreatorSubscription).toHaveBeenCalledWith("creator-1", true);

    await user.click(screen.getByRole("button", { name: "返回全部归档" }));
    await waitFor(() => expect(api.fetchFeed).toHaveBeenLastCalledWith(expect.objectContaining({ creatorId: undefined })));
  });

  it("switches to the multi-post grid and remembers the preference", async () => {
    vi.mocked(api.fetchFeed).mockResolvedValue({
      items: [itemFor(collections[0]), itemFor(collections[1])],
      nextCursor: null,
    });
    const user = userEvent.setup();
    render(<FeedPage />);

    await user.click(await screen.findByRole("button", { name: "多作品视图" }));

    expect(screen.getByTestId("feed-grid")).toBeVisible();
    expect(screen.getAllByRole("button", { name: /\u6253\u5f00\u4f5c\u54c1/ })).toHaveLength(2);
    expect(window.localStorage.getItem("liuying.feedView.v1")).toBe("grid");
  });

  it("opens the selected grid post in the single-post view", async () => {
    vi.mocked(api.fetchFeed).mockResolvedValue({
      items: [itemFor(collections[0]), itemFor(collections[1])],
      nextCursor: null,
    });
    const user = userEvent.setup();
    render(<FeedPage />);
    await user.click(await screen.findByRole("button", { name: "多作品视图" }));

    await user.click(screen.getByRole("button", { name: "打开作品：来自 好看的美女" }));

    expect(screen.getByRole("button", { name: "单个作品视图" })).toHaveAttribute("aria-pressed", "true");
    expect(within(screen.getByTestId("feed-card-active")).getByRole("heading", { name: "来自 好看的美女" })).toBeVisible();
  });

  it("restores the saved multi-post preference", async () => {
    window.localStorage.setItem("liuying.feedView.v1", "grid");

    render(<FeedPage />);

    expect(await screen.findByTestId("feed-grid")).toBeVisible();
    expect(screen.getByRole("button", { name: "多作品视图" })).toHaveAttribute("aria-pressed", "true");
  });

  it("exposes stable safe-area structure for the iphone viewport", async () => {
    render(<FeedPage />);
    const feed = await screen.findByTestId("archive-feed-root");
    expect(feed).toHaveClass("iphone-feed-shell");
    const navigation = screen.getByRole("navigation", { name: "移动导航" });
    expect(navigation).toHaveClass("iphone-bottom-nav", "friendly-mobile-nav");
    expect(within(navigation).getAllByRole("button").every((button) => button.classList.contains("touch-target"))).toBe(true);
  });

  it("keeps auto-paginating for each distinct cursor in the multi-post grid", async () => {
    const observers: Array<{ callback: IntersectionObserverCallback; elements: Element[]; instance: IntersectionObserver }> = [];
    class FakeIntersectionObserver {
      readonly root = null;
      readonly rootMargin = "0px";
      readonly thresholds = [0];
      readonly elements: Element[] = [];
      constructor(readonly callback: IntersectionObserverCallback) {
        observers.push({ callback, elements: this.elements, instance: this as unknown as IntersectionObserver });
      }
      observe = (element: Element) => { this.elements.push(element); };
      disconnect = vi.fn();
      unobserve = vi.fn();
      takeRecords = () => [];
    }
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);
    window.localStorage.setItem("liuying.feedView.v1", "grid");
    const thirdCollection = { id: "1003", name: "第三页", itemCount: 1, lastSeenAt: 1 };
    const fourthCollection = { id: "1004", name: "第四页", itemCount: 1, lastSeenAt: 1 };
    vi.mocked(api.fetchFeed)
      .mockResolvedValueOnce({ items: [itemFor(collections[0])], nextCursor: "page-2" })
      .mockResolvedValueOnce({ items: [itemFor(collections[1])], nextCursor: "page-3" })
      .mockResolvedValueOnce({ items: [itemFor(thirdCollection)], nextCursor: "page-4" })
      .mockResolvedValueOnce({ items: [itemFor(fourthCollection)], nextCursor: null });
    const view = render(<FeedPage />);

    await screen.findByTestId("feed-grid");
    expect(screen.queryByRole("button", { name: "加载更多" })).not.toBeInTheDocument();

    for (const cursor of ["page-2", "page-3", "page-4"]) {
      const sentinel = view.container.querySelector(".pagination-sentinel");
      expect(sentinel).not.toBeNull();
      await waitFor(() => expect(observers.some((observer) => observer.elements.includes(sentinel!))).toBe(true));
      const paginationObserver = observers.filter((observer) => observer.elements.includes(sentinel!)).at(-1)!;
      act(() => {
        paginationObserver.callback([
          { isIntersecting: true, intersectionRatio: 1, target: sentinel },
          { isIntersecting: true, intersectionRatio: 1, target: sentinel },
        ] as unknown as IntersectionObserverEntry[], paginationObserver.instance);
      });
      await waitFor(() => expect(api.fetchFeed).toHaveBeenCalledWith(expect.objectContaining({ cursor })));
      expect(vi.mocked(api.fetchFeed).mock.calls.filter(([request]) => request.cursor === cursor)).toHaveLength(1);
    }

    await waitFor(() => expect(view.container.querySelectorAll(".archive-grid-card")).toHaveLength(4));
    expect(view.container.querySelector(".pagination-sentinel")).toBeNull();
  });
});
