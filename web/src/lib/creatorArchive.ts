import type { Creator, CreatorArchiveStatus, FeedItem } from "../app/api";
import { t } from "../i18n/t";

export const ARCHIVE_STATUS_LABEL: Record<Exclude<CreatorArchiveStatus, "active">, string> = {
  reset: t("资料被重置"),
  deactivated: t("已注销"),
  banned: t("已封禁"),
  vanished: t("作品已清空"),
};

export const ARCHIVE_STATUS_HINT: Record<Exclude<CreatorArchiveStatus, "active">, string> = {
  reset: t("抖音把昵称换成了一串数字、头像换成了默认头像，通常是违规后被处理，作品可能很快消失。"),
  deactivated: t("账号已经注销，抖音上只剩“该用户已注销”。"),
  banned: t("抖音上已经打不开这个账号。"),
  vanished: t("账号还在，但公开作品已经全部消失。"),
};

export function isArchived(creator: Creator | null | undefined): boolean {
  return Boolean(creator?.archive && creator.archive.status !== "active");
}

/** Names the creator chose over time, oldest first, without Douyin's placeholders. */
export function formerNames(creator: Creator): string[] {
  const names: string[] = [];
  for (const snapshot of creator.archive?.history ?? []) {
    if (!snapshot.degraded && !names.includes(snapshot.nickname)) names.push(snapshot.nickname);
  }
  return names.filter((name) => name !== creator.nickname);
}

/** A work whose video we lack: "lost" can no longer be fetched, "at-risk" may still be. */
export function unsavedWorkRisk(item: FeedItem): "lost" | "at-risk" | null {
  const status = item.creator?.archiveStatus;
  if (!status || status === "active" || item.local.state === "downloaded") return null;
  return status === "banned" || status === "vanished" ? "lost" : "at-risk";
}
