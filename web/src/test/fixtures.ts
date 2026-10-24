import type { FeedItem, SyncHealth } from "../app/api";

export function makeItem(overrides: Partial<FeedItem> = {}): FeedItem {
  const id = overrides.awemeId ?? "7000000000000000001";
  return {
    awemeId: id,
    creatorId: "c1",
    author: "小鹿",
    description: `作品 ${id.slice(-2)}`,
    type: "video",
    publishedAt: 1_700_000_000,
    archivedAt: 1_700_000_100,
    sourceUrl: null,
    coverUrl: null,
    thumbnailUrl: `/api/media/${id.slice(-3)}/poster`,
    starred: false,
    starredAt: null,
    creator: { id: "c1", nickname: "小鹿", uniqueId: "deer", avatarUrl: null },
    douyin: { statistics: { diggCount: 1200 }, durationMs: 15_000, hashtags: ["旅行"], music: null, visibility: "public" },
    collections: [],
    media: [
      {
        id: Number(id.slice(-3)),
        index: 0,
        type: "video",
        byteSize: 1024,
        mimeType: "video/mp4",
        url: `/api/media/${id.slice(-3)}`,
        posterUrl: `/api/media/${id.slice(-3)}/poster`,
      },
    ],
    local: { state: "downloaded", readyAssets: 1, totalAssets: 1, downloadedBytes: 1024, totalBytes: 1024 },
    ...overrides,
  };
}

export function makeHealth(overrides: Partial<SyncHealth> = {}): SyncHealth {
  return {
    state: "ok",
    lastSuccessAt: Math.round(Date.now() / 1000) - 120,
    lastAttemptAt: Math.round(Date.now() / 1000) - 120,
    lastErrorCode: null,
    consecutiveFailures: 0,
    intervalSeconds: 300,
    staleAfterSeconds: 1800,
    browser: "ok",
    ...overrides,
  };
}
