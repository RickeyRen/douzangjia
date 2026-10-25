import { CloudArrowDown, CloudSlash, ImageSquare, Images, Play, Star } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

import type { FeedItem } from "../app/api";
import { formatDuration } from "../lib/format";
import { itemDurationMs, itemImageCount, itemTitle, placeholderStyle, thumbnailCandidates } from "./itemInfo";
import { Avatar } from "../ui/primitives";
import { t } from "../i18n/t";

export function Thumbnail({ item, className }: { item: FeedItem; className?: string }) {
  const candidates = thumbnailCandidates(item);
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const src = candidates[attempt];
  if (!src) {
    return (
      <span className="tile-placeholder" style={placeholderStyle(item.awemeId)} data-testid="tile-placeholder">
        <span>
          <ImageSquare size={28} weight="duotone" />
          <p>{itemTitle(item)}</p>
        </span>
      </span>
    );
  }
  return (
    <img
      key={src}
      className={className}
      src={src}
      alt=""
      loading="lazy"
      decoding="async"
      draggable={false}
      referrerPolicy="no-referrer"
      data-loaded={loaded}
      onLoad={() => setLoaded(true)}
      onError={() => {
        setLoaded(false);
        setAttempt((value) => value + 1);
      }}
    />
  );
}

export function MediaTile({
  item,
  onOpen,
  onOpenCreator,
  showMeta = true,
  selectable = false,
  selected = false,
  aspect,
  preview = true,
}: {
  item: FeedItem;
  onOpen: (event: { shiftKey: boolean }) => void;
  onOpenCreator?: (creatorId: string | null, name: string) => void;
  showMeta?: boolean;
  selectable?: boolean;
  selected?: boolean;
  /** CSS aspect-ratio override (natural grid mode). */
  aspect?: number;
  preview?: boolean;
}) {
  const [hovering, setHovering] = useState(false);
  const hoverTimer = useRef<number | undefined>(undefined);
  const videoUrl = item.type === "video" && item.local.state === "downloaded" ? item.media.find((media) => media.type === "video")?.url : undefined;
  const canPreview = preview && Boolean(videoUrl) && typeof window !== "undefined" && window.matchMedia?.("(hover: hover)").matches;

  useEffect(() => () => window.clearTimeout(hoverTimer.current), []);

  function enter() {
    if (!canPreview) return;
    window.clearTimeout(hoverTimer.current);
    hoverTimer.current = window.setTimeout(() => setHovering(true), 450);
  }

  function leave() {
    window.clearTimeout(hoverTimer.current);
    setHovering(false);
  }
  const duration = formatDuration(itemDurationMs(item));
  const images = item.type === "gallery" ? itemImageCount(item) : 0;
  const local = item.local.state === "downloaded";
  const name = item.creator?.nickname || item.author;
  return (
    <article className={`tile${selectable ? " is-selectable" : ""}${selected ? " is-selected" : ""}`} onMouseEnter={enter} onMouseLeave={leave}>
      <button
        type="button"
        className="tile-media"
        style={aspect ? { aspectRatio: String(aspect) } : undefined}
        onClick={(event) => onOpen({ shiftKey: event.shiftKey })}
        aria-label={`${selectable ? (selected ? t("取消选择：") : t("选择：")) : t("打开作品：")}${itemTitle(item)}`}
        aria-pressed={selectable ? selected : undefined}
      >
        {selectable ? <span className="tile-check">{selected ? <CheckGlyph /> : null}</span> : null}
        <Thumbnail item={item} />
        {hovering && videoUrl ? <video className="tile-preview" src={videoUrl} muted autoPlay loop playsInline preload="auto" data-testid="tile-preview" /> : null}
        <span className="tile-tags">
          <span>
            {item.starred ? (
              <span className="tile-tag is-star" title={t("精选")}>
                <Star size={11} weight="fill" />
              </span>
            ) : null}
            {item.remoteAvailability && ["deleted", "private"].includes(item.remoteAvailability.status) ? (
              <span className="tile-tag is-gone" title={t("抖音上已消失")}>
                <CloudSlash size={11} weight="bold" />
                {t("已消失")}
              </span>
            ) : null}
          </span>
          <span>
            {!local ? (
              <span className="tile-tag is-cloud" title={t("尚未下载到 NAS")}>
                <CloudArrowDown size={12} weight="bold" />
              </span>
            ) : null}
            {item.type === "gallery" ? (
              <span className="tile-tag">
                <Images size={11} weight="fill" />
                {images > 0 ? images : null}
              </span>
            ) : (
              <span className="tile-tag">
                <Play size={10} weight="fill" />
                {duration}
              </span>
            )}
          </span>
        </span>
        <span className="tile-bottom">
          <span className="tile-title">{itemTitle(item)}</span>
        </span>
      </button>
      {showMeta ? (
        <div className="tile-meta">
          <Avatar src={item.creator?.avatarUrl} name={name} />
          {onOpenCreator ? (
            <button type="button" onClick={() => onOpenCreator(item.creatorId, name)}>
              <span>{name}</span>
            </button>
          ) : (
            <span>{name}</span>
          )}
        </div>
      ) : null}
    </article>
  );
}

function CheckGlyph() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
      <path d="M2.5 6.5l2.5 2.5 4.5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function TileSkeleton() {
  return (
    <div className="tile tile-skeleton" aria-hidden="true">
      <div className="tile-media" />
      <div className="tile-meta" />
    </div>
  );
}
