import type { FeedItem } from "../app/api";

export function itemTitle(item: FeedItem): string {
  return item.description.trim() || `@${item.author}`;
}

export function itemDurationMs(item: FeedItem): number | null {
  return item.douyin?.durationMs ?? item.media.find((media) => media.type === "video")?.technical?.durationMs ?? null;
}

export function itemImageCount(item: FeedItem): number {
  return Math.max(item.local.totalAssets, item.media.filter((media) => media.type === "image").length);
}

/** Candidate thumbnails in order: local poster, Douyin cover, then nothing. */
export function thumbnailCandidates(item: FeedItem): string[] {
  const candidates = [item.thumbnailUrl, item.media[0]?.posterUrl, item.coverUrl].filter(
    (value): value is string => Boolean(value),
  );
  return [...new Set(candidates)];
}

export function douyinUrl(item: FeedItem): string {
  return item.sourceUrl || `https://www.douyin.com/${item.type === "gallery" ? "note" : "video"}/${item.awemeId}`;
}
