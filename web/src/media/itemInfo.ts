import type { FeedItem } from "../app/api";

/** A stable, pleasant hue per item so cover-less tiles look designed, not broken. */
export function placeholderStyle(id: string): { background: string } {
  let hash = 7;
  for (const char of id) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  const hue = hash % 360;
  const hue2 = (hue + 40) % 360;
  return { background: `linear-gradient(160deg, hsl(${hue} 38% 28%), hsl(${hue2} 42% 16%))` };
}

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

/** Width / height from probed media, clamped so odd files stay tidy. */
export function aspectOf(item: FeedItem): number {
  const technical = item.media[0]?.technical;
  if (technical?.width && technical.height) return Math.min(1.78, Math.max(0.56, technical.width / technical.height));
  return 0.75;
}
