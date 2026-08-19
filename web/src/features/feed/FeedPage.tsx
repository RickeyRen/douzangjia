import { CaretDown, CaretLeft, CaretRight, DownloadSimple, Folders, MagnifyingGlass, X } from "@phosphor-icons/react";
import { useCallback, useDeferredValue, useEffect, useRef, useState } from "react";

import { archiveCreator, archiveItem, archiveSource, fetchCollections, fetchCreator, fetchFeed, updateCreatorSubscription, type Collection, type Creator, type FeedItem } from "../../app/api";
import { FriendlyIconButton } from "../../components/FriendlyIconButton";
import { useI18n } from "../../i18n/context";
import { ThemeToggle } from "../../theme/ThemeToggle";
import { CollectionRail } from "../navigation/CollectionRail";
import type { UtilityPanel } from "../navigation/CollectionRail";
import { MobileNavigation, type MobileDestination } from "../navigation/MobileNavigation";
import { ArchiveStatusPanel } from "../status/ArchiveStatusPanel";
import { DesktopItemDetails } from "./DesktopItemDetails";
import { CreatorProfile } from "./CreatorProfile";
import { FeedCard } from "./FeedCard";
import { FeedGrid } from "./FeedGrid";
import { FeedViewToggle, type FeedViewMode } from "./FeedViewToggle";
import { ItemDetailsSheet } from "./ItemDetailsSheet";
import { MobileSearchSheet } from "./MobileSearchSheet";

export function feedIndexFromTarget(target: HTMLElement): number {
  const index = Number(target.dataset.feedIndex);
  return Number.isInteger(index) && index >= 0 ? index : 0;
}

export function shouldAutoPaginate(activeIndex: number, itemCount: number): boolean {
  return itemCount > 0 && activeIndex >= Math.max(0, itemCount - 3);
}

const feedViewStorageKey = "liuying.feedView.v1";

function savedFeedView(): FeedViewMode {
  try {
    return window.localStorage.getItem(feedViewStorageKey) === "grid" ? "grid" : "focus";
  } catch {
    return "focus";
  }
}

export function FeedPage() {
  const { t } = useI18n();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selected, setSelected] = useState<string | undefined>();
  const [selectedCreator, setSelectedCreator] = useState<{ id: string | null; name: string } | null>(null);
  const [creator, setCreator] = useState<Creator | null>(null);
  const [viewMode, setViewMode] = useState<FeedViewMode>(savedFeedView);
  const [items, setItems] = useState<FeedItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [detailItem, setDetailItem] = useState<FeedItem | null>(null);
  const [utilityPanel, setUtilityPanel] = useState<UtilityPanel | null>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const paginationSentinel = useRef<HTMLDivElement>(null);
  const feedRequestId = useRef(0);
  const loadingMoreRef = useRef(false);
  const autoPaginatedCursor = useRef<string | null>(null);
  const pendingFocusIndex = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    void fetchCollections()
      .then((result) => {
        if (!cancelled) setCollections(result.items);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!selectedCreator?.id) {
      setCreator(null);
      return () => { cancelled = true; };
    }
    void fetchCreator(selectedCreator.id)
      .then((value) => { if (!cancelled) setCreator(value); })
      .catch(() => { if (!cancelled) setCreator(null); });
    return () => { cancelled = true; };
  }, [selectedCreator]);

  useEffect(() => {
    let cancelled = false;
    const requestId = ++feedRequestId.current;
    setLoading(true);
    setError(false);
    setLoadMoreError(false);
    setNextCursor(null);
    loadingMoreRef.current = false;
    autoPaginatedCursor.current = null;
    void fetchFeed({ collectionId: selectedCreator ? undefined : selected, creatorId: selectedCreator?.id ?? undefined, author: selectedCreator && !selectedCreator.id ? selectedCreator.name : undefined, search: deferredSearch || undefined })
      .then((result) => {
        if (!cancelled && requestId === feedRequestId.current) {
          setItems(result.items);
          setNextCursor(result.nextCursor);
          setActiveIndex(0);
        }
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [deferredSearch, selected, selectedCreator]);

  useEffect(() => {
    const root = viewport.current;
    if (!root || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.find((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.72);
        if (visible) setActiveIndex(feedIndexFromTarget(visible.target as HTMLElement));
      },
      { root, threshold: [0.72] },
    );
    root.querySelectorAll("[data-feed-index]").forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [items, viewMode]);

  useEffect(() => {
    if (viewMode !== "focus" || pendingFocusIndex.current === null) return;
    const index = pendingFocusIndex.current;
    pendingFocusIndex.current = null;
    viewport.current?.querySelector<HTMLElement>(`[data-feed-index="${index}"]`)?.scrollIntoView?.({ block: "start" });
  }, [items, viewMode]);

  const active = items[activeIndex];
  const selectedName = collections.find((item) => item.id === selected)?.name ?? t("allArchives");

  function move(direction: -1 | 1) {
    const next = Math.max(0, Math.min(items.length - 1, activeIndex + direction));
    viewport.current?.querySelector<HTMLElement>(`[data-feed-index="${next}"]`)?.scrollIntoView({ behavior: "smooth" });
    setActiveIndex(next);
  }

  const loadMore = useCallback(async () => {
    if (!nextCursor || loadingMoreRef.current) return;
    const requestedCursor = nextCursor;
    const requestId = feedRequestId.current;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    setLoadMoreError(false);
    try {
      const result = await fetchFeed({ collectionId: selectedCreator ? undefined : selected, creatorId: selectedCreator?.id ?? undefined, author: selectedCreator && !selectedCreator.id ? selectedCreator.name : undefined, search: deferredSearch || undefined, cursor: requestedCursor });
      if (requestId !== feedRequestId.current) return;
      setItems((current) => {
        const known = new Set(current.map((item) => item.awemeId));
        return [...current, ...result.items.filter((item) => !known.has(item.awemeId))];
      });
      setNextCursor(result.nextCursor);
    } catch {
      if (requestId === feedRequestId.current) {
        if (autoPaginatedCursor.current === requestedCursor) autoPaginatedCursor.current = null;
        setLoadMoreError(true);
      }
    } finally {
      loadingMoreRef.current = false;
      if (requestId === feedRequestId.current) setLoadingMore(false);
    }
  }, [deferredSearch, nextCursor, selected, selectedCreator]);

  useEffect(() => {
    const target = paginationSentinel.current;
    const root = viewport.current;
    if (!target || !root || !nextCursor || loadMoreError || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver((entries) => {
      if (
        (viewMode === "grid" || shouldAutoPaginate(activeIndex, items.length))
        && autoPaginatedCursor.current !== nextCursor
        && entries.some((entry) => entry.isIntersecting)
      ) {
        autoPaginatedCursor.current = nextCursor;
        void loadMore();
      }
    }, { root, rootMargin: "0px 0px 100% 0px", threshold: 0.01 });
    observer.observe(target);
    return () => observer.disconnect();
  }, [activeIndex, items.length, loadMore, loadMoreError, nextCursor, viewMode]);

  function openMobileDestination(destination: MobileDestination) {
    if (destination === "collections") setDrawerOpen(true);
    else if (destination === "search") setSearchOpen(true);
    else if (destination === "activity" || destination === "settings") setUtilityPanel(destination);
    else if (destination === "feed") {
      setDrawerOpen(false);
      setUtilityPanel(null);
    }
  }

  function openAuthor(creatorId: string | null, author: string) {
    setSelectedCreator({ id: creatorId, name: author });
    setSearch("");
    setDetailItem(null);
  }

  function selectCollection(id?: string) {
    setSelectedCreator(null);
    setSelected(id);
  }

  function changeViewMode(mode: FeedViewMode, focusIndex = activeIndex) {
    if (mode === "focus") pendingFocusIndex.current = focusIndex;
    setViewMode(mode);
    try {
      window.localStorage.setItem(feedViewStorageKey, mode);
    } catch {
      // Private browsing can reject storage; the in-memory preference still works.
    }
  }

  function openGridItem(index: number) {
    setActiveIndex(index);
    changeViewMode("focus", index);
  }

  async function archivePost(item: FeedItem) {
    await archiveItem(item.awemeId);
    setUtilityPanel("downloads");
  }

  async function archiveAllCreatorPosts() {
    if (!selectedCreator?.id) return;
    await archiveCreator(selectedCreator.id);
    setUtilityPanel("downloads");
  }

  async function archiveSelectedSource() {
    if (!selected) return;
    await archiveSource(`favorite_collection:${selected}`);
    setUtilityPanel("downloads");
  }

  async function toggleCreatorSubscription(enabled: boolean) {
    if (!selectedCreator?.id) return;
    const subscription = await updateCreatorSubscription(selectedCreator.id, enabled);
    setCreator((current) => current ? { ...current, subscription } : current);
  }

  return (
    <main data-testid="archive-feed-root" className="iphone-feed-shell archive-app-shell">
      <div data-testid="desktop-workspace" className={`archive-desktop-grid${viewMode === "grid" ? " is-grid-view" : ""}`}>
        <CollectionRail collections={collections} selected={selectedCreator ? undefined : selected} onSelect={selectCollection} onOpenPanel={setUtilityPanel} />
        <section data-testid="desktop-content" className="archive-content-column friendly-panel">
          <header className="archive-topbar">
            {selectedCreator ? (
              <div className="creator-archive-heading">
                <FriendlyIconButton label={t("backToArchive")} onClick={() => setSelectedCreator(null)}><CaretLeft size={20} weight="bold" /></FriendlyIconButton>
                <div><span>{t("creatorArchive")}</span><h1>@{selectedCreator.name}</h1></div>
              </div>
            ) : (
              <button className="archive-collection-trigger" type="button" onClick={() => setDrawerOpen(true)}>
                <span className="archive-mobile-brand">{t("brand")}</span>
                <span>{selectedName}</span>
                <CaretDown className="archive-mobile-only" size={17} weight="bold" />
              </button>
            )}
            {selected && !selectedCreator ? (
              <FriendlyIconButton label={t("archiveCurrentSource")} onClick={() => void archiveSelectedSource()}>
                <DownloadSimple size={20} weight="bold" />
              </FriendlyIconButton>
            ) : null}
            <label className="archive-search-field">
              <MagnifyingGlass size={20} weight="bold" />
              <input aria-label={t("searchArchive")} value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("searchArchive")} />
            </label>
            <FeedViewToggle mode={viewMode} onChange={changeViewMode} />
            <ThemeToggle />
            <FriendlyIconButton label={t("searchArchive")} onClick={() => setSearchOpen(true)} className="archive-mobile-search">
              <MagnifyingGlass size={21} weight="bold" />
            </FriendlyIconButton>
          </header>

          <div className="archive-feed-region">
            {creator ? <CreatorProfile creator={creator} onArchiveAll={archiveAllCreatorPosts} onToggleSubscription={toggleCreatorSubscription} /> : null}
            {loading ? <FeedSkeleton label={t("loadingArchive")} /> : error ? <ErrorState label={t("feedError")} retry={t("retry")} /> : items.length === 0 ? <EmptyState title={t(selectedCreator ? "creatorEmptyTitle" : "emptyTitle")} body={t(selectedCreator ? "creatorEmptyBody" : "emptyBody")} /> : (
              <div ref={viewport} className={viewMode === "grid" ? "archive-grid-viewport" : "feed-viewport snap-y snap-mandatory overflow-y-auto"}>
                {viewMode === "grid" ? <FeedGrid items={items} activeIndex={activeIndex} onOpen={openGridItem} /> : items.map((item, index) => (
                    <div key={item.awemeId} data-feed-index={index}>
                      <FeedCard item={item} active={index === activeIndex} onOpenDetails={setDetailItem} onOpenCollections={() => setDrawerOpen(true)} onOpenAuthor={openAuthor} onArchiveItem={(entry) => void archivePost(entry)} />
                    </div>
                  ))}
                {nextCursor || loadMoreError ? (
                  <div ref={paginationSentinel} className="pagination-sentinel flex min-h-20 snap-start snap-always items-center justify-center pb-[calc(96px+env(safe-area-inset-bottom))] pt-3">
                    {loadMoreError ? (
                      <button type="button" disabled={loadingMore} onClick={() => void loadMore()} className="friendly-button friendly-button-secondary touch-target">
                        {loadingMore ? t("loadingMore") : t("retryLoadMore")}
                      </button>
                    ) : (
                      <span role="status" aria-live="polite" className="pagination-background-status">
                        {loadingMore ? t("loadingMore") : ""}
                      </span>
                    )}
                  </div>
                ) : null}
              </div>
            )}
          </div>

          {active && viewMode === "focus" ? (
            <footer className="archive-desktop-pager">
              <FriendlyIconButton label={t("previousItem")} disabled={activeIndex === 0} onClick={() => move(-1)}><CaretLeft size={21} weight="bold" /></FriendlyIconButton>
              <span>{activeIndex + 1} / {items.length}</span>
              <FriendlyIconButton label={t("nextItem")} disabled={activeIndex === items.length - 1} onClick={() => move(1)}><CaretRight size={21} weight="bold" /></FriendlyIconButton>
            </footer>
          ) : null}
        </section>
        {viewMode === "focus" ? active ? <DesktopItemDetails item={active} onOpenAuthor={openAuthor} /> : <aside data-testid="desktop-details" className="desktop-item-details friendly-panel desktop-details-empty" /> : null}
      </div>

      {drawerOpen ? <CollectionDrawer collections={collections} selected={selected} onSelect={(id) => { selectCollection(id); setDrawerOpen(false); }} onClose={() => setDrawerOpen(false)} /> : null}
      {utilityPanel ? <ArchiveStatusPanel kind={utilityPanel} onClose={() => setUtilityPanel(null)} /> : null}
      {searchOpen ? <MobileSearchSheet value={search} onChange={setSearch} onClose={() => setSearchOpen(false)} /> : null}
      {detailItem ? <ItemDetailsSheet item={detailItem} onClose={() => setDetailItem(null)} onOpenAuthor={openAuthor} /> : null}
      <MobileNavigation onOpen={openMobileDestination} />
    </main>
  );
}

function CollectionDrawer({ collections, selected, onSelect, onClose }: { collections: Collection[]; selected?: string; onSelect: (id?: string) => void; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <div className="collection-drawer-overlay" onClick={onClose}>
      <section role="dialog" aria-modal="true" aria-label={t("switchCollection")} className="collection-drawer" onClick={(event) => event.stopPropagation()}>
        <div className="drawer-handle" />
        <div className="collection-drawer-header"><h2>{t("switchCollection")}</h2><button aria-label={t("closeDrawer")} className="utility-close-button" onClick={onClose}><X size={20} /></button></div>
        <div className="collection-drawer-list">
          {[{ id: undefined, name: t("allArchives") }, ...collections].map((item) => (
            <button key={item.id ?? "all"} onClick={() => onSelect(item.id)} className={`collection-drawer-item${item.id === selected ? " is-active" : ""}`}><Folders size={19} />{item.name}</button>
          ))}
        </div>
        <p className="collection-drawer-footer">{t("autoSync")}</p>
      </section>
    </div>
  );
}

function FeedSkeleton({ label }: { label: string }) {
  return <div className="feed-state"><div><div className="feed-skeleton-frame animate-pulse" /><p>{label}</p></div></div>;
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return <div className="feed-state"><div><Folders size={38} weight="regular" /><h2>{title}</h2><p>{body}</p></div></div>;
}

function ErrorState({ label, retry }: { label: string; retry: string }) {
  return <div className="feed-state"><div><p>{label}</p><button className="friendly-button friendly-button-secondary" onClick={() => window.location.reload()}>{retry}</button></div></div>;
}
