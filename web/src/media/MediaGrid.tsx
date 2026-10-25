import { useEffect, useRef } from "react";

import type { FeedItem } from "../app/api";
import { Spinner } from "../ui/primitives";
import { MediaTile, TileSkeleton } from "./MediaTile";

export function MediaGrid({
  items,
  loading,
  loadingMore = false,
  hasMore = false,
  error = false,
  onLoadMore,
  onRetry,
  onOpen,
  onOpenCreator,
  showMeta = true,
  selected,
  onToggleSelect,
}: {
  items: FeedItem[];
  loading: boolean;
  loadingMore?: boolean;
  hasMore?: boolean;
  error?: boolean;
  onLoadMore?: () => void;
  onRetry?: () => void;
  onOpen: (index: number) => void;
  onOpenCreator?: (creatorId: string | null, name: string) => void;
  showMeta?: boolean;
  /** When present the grid is in selection mode and tiles toggle instead of opening. */
  selected?: Set<string>;
  onToggleSelect?: (index: number, range: boolean) => void;
}) {
  const sentinel = useRef<HTMLDivElement>(null);
  const loadMoreRef = useRef(onLoadMore);
  loadMoreRef.current = onLoadMore;

  useEffect(() => {
    const target = sentinel.current;
    if (!target || !hasMore || error || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) loadMoreRef.current?.();
      },
      { rootMargin: "900px 0px" },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [error, hasMore, items.length]);

  if (loading) {
    return (
      <div className="grid" aria-busy="true" aria-label="正在加载">
        {Array.from({ length: 12 }, (_, index) => (
          <TileSkeleton key={index} />
        ))}
      </div>
    );
  }

  return (
    <>
      <div className="grid" data-testid="media-grid">
        {items.map((item, index) => (
          <MediaTile
            key={item.awemeId}
            item={item}
            onOpen={(event) => (selected ? onToggleSelect?.(index, event.shiftKey) : onOpen(index))}
            onOpenCreator={onOpenCreator}
            showMeta={showMeta}
            selectable={selected !== undefined}
            selected={selected?.has(item.awemeId) ?? false}
          />
        ))}
      </div>
      <div ref={sentinel} className="grid-footer">
        {error ? (
          <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
            加载失败，点此重试
          </button>
        ) : loadingMore ? (
          <Spinner />
        ) : !hasMore && items.length > 12 ? (
          <span>已经到底了 · 共 {items.length} 个</span>
        ) : null}
      </div>
    </>
  );
}
