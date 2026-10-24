import { FolderSimple } from "@phosphor-icons/react";

import { EMOJI_PREFIX, SOURCE_ICONS, type SourceLike } from "./sourceMeta";

export function SourceIcon({ source, size = 18 }: { source: SourceLike; size?: number }) {
  if (source.kind === "favorite_collection" && EMOJI_PREFIX.test(source.name)) {
    return <span className="nav-emoji">{[...source.name][0]}</span>;
  }
  const Glyph = SOURCE_ICONS[source.kind] ?? FolderSimple;
  return <Glyph size={size} weight="regular" />;
}
