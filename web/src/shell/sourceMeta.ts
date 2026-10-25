import {
  BookmarkSimple,
  CalendarCheck,
  Clock,
  ClockCounterClockwise,
  FilmSlate,
  FolderSimple,
  Heart,
  MusicNotes,
  Sparkle,
  Stack,
  UserPlus,
  VideoCamera,
  type Icon,
} from "@phosphor-icons/react";

import type { LibrarySource } from "../app/api";
import { t } from "../i18n/t";

export const SOURCE_ICONS: Record<LibrarySource["kind"], Icon> = {
  favorite_collection: FolderSimple,
  favorite_video: BookmarkSimple,
  like: Heart,
  post: VideoCamera,
  watch_history: ClockCounterClockwise,
  watch_later: Clock,
  recommend: Sparkle,
  favorite_music: MusicNotes,
  favorite_series: Stack,
  favorite_drama: FilmSlate,
  reservation: CalendarCheck,
  following: UserPlus,
};

/** Sources that hold entities (music, series…) rather than playable items. */
export const ENTITY_SOURCE_KINDS = new Set<LibrarySource["kind"]>(["favorite_music"]);

const ACCOUNT_ORDER: LibrarySource["kind"][] = [
  "favorite_video",
  "like",
  "post",
  "watch_later",
  "watch_history",
  "recommend",
  "favorite_series",
  "favorite_drama",
  "favorite_music",
  "reservation",
  "following",
];

export function groupSources(sources: LibrarySource[]) {
  const collections = sources
    .filter((source) => source.kind === "favorite_collection")
    .sort((a, b) => b.discoveredCount - a.discoveredCount);
  const account = sources
    .filter((source) => source.kind !== "favorite_collection")
    .sort((a, b) => ACCOUNT_ORDER.indexOf(a.kind) - ACCOUNT_ORDER.indexOf(b.kind));
  return {
    collections,
    accountActive: account.filter((source) => source.discoveredCount > 0),
    accountEmpty: account.filter((source) => source.discoveredCount === 0),
  };
}

export const EMOJI_PREFIX = /^\p{Extended_Pictographic}/u;

export type SourceLike = Pick<LibrarySource, "kind" | "name">;

export function sourceLabel(source: SourceLike): string {
  // The icon already shows a leading emoji, so the label keeps only the words.
  if (source.kind !== "favorite_collection") return source.name;
  const words = source.name.replace(EMOJI_PREFIX, "").replace(/^[\uFE0F\s]+/u, "").trim();
  return words || t("收藏夹");
}
