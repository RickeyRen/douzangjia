import { ImageSquare, Play } from "@phosphor-icons/react";

import type { FeedItem } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { LocalStateBadge } from "./LocalStateBadge";

export function FeedGrid({ items, activeIndex, onOpen }: { items: FeedItem[]; activeIndex: number; onOpen: (index: number) => void }) {
  const { t } = useI18n();
  return (
    <div data-testid="feed-grid" className="archive-feed-grid">
      {items.map((item, index) => {
        const media = item.media[0];
        const title = item.description || `@${item.author}`;
        return (
          <article key={item.awemeId} className={`archive-grid-card${index === activeIndex ? " is-current" : ""}`}>
            <button type="button" aria-label={`${t("openPostPrefix")}${title}`} onClick={() => onOpen(index)}>
              {media ? item.type === "gallery" || media.type === "image" ? (
                <img src={media.url} alt="" loading="lazy" draggable={false} />
              ) : (
                <video src={media.url} muted playsInline preload="metadata" />
              ) : (
                <span className="archive-grid-placeholder"><ImageSquare size={30} weight="duotone" /></span>
              )}
              {item.type === "video" ? <span className="archive-grid-type"><Play size={13} weight="fill" /></span> : null}
              <LocalStateBadge local={item.local} />
              <span className="archive-grid-caption">
                <strong>{title}</strong>
                <small>@{item.author}</small>
              </span>
            </button>
          </article>
        );
      })}
    </div>
  );
}
