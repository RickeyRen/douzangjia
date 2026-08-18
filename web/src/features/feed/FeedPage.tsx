import { CaretDown, CaretUp, Folders, MagnifyingGlass, X } from "@phosphor-icons/react";
import { useCallback, useDeferredValue, useEffect, useRef, useState } from "react";

import { fetchCollections, fetchFeed, type Collection, type FeedItem } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { CollectionRail } from "../navigation/CollectionRail";
import type { UtilityPanel } from "../navigation/CollectionRail";
import { MobileNavigation, type MobileDestination } from "../navigation/MobileNavigation";
import { ArchiveStatusPanel } from "../status/ArchiveStatusPanel";
import { FeedCard } from "./FeedCard";
import { ItemDetailsSheet } from "./ItemDetailsSheet";
import { MobileSearchSheet } from "./MobileSearchSheet";

export function feedIndexFromTarget(target: HTMLElement): number {
  const index = Number(target.dataset.feedIndex);
  return Number.isInteger(index) && index >= 0 ? index : 0;
}

export function shouldAutoPaginate(activeIndex: number, itemCount: number): boolean {
  return itemCount > 0 && activeIndex >= Math.max(0, itemCount - 3);
}

export function FeedPage() {
  const { t } = useI18n();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selected, setSelected] = useState<string | undefined>();
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
  const autoPaginatedRequestId = useRef<number | null>(null);

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
    const requestId = ++feedRequestId.current;
    setLoading(true);
    setError(false);
    setLoadMoreError(false);
    setNextCursor(null);
    loadingMoreRef.current = false;
    autoPaginatedRequestId.current = null;
    void fetchFeed({ collectionId: selected, search: deferredSearch || undefined })
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
  }, [deferredSearch, selected]);

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
  }, [items]);

  const active = items[activeIndex];
  const selectedName = collections.find((item) => item.id === selected)?.name ?? t("allArchives");

  function move(direction: -1 | 1) {
    const next = Math.max(0, Math.min(items.length - 1, activeIndex + direction));
    viewport.current?.querySelector<HTMLElement>(`[data-feed-index="${next}"]`)?.scrollIntoView({ behavior: "smooth" });
    setActiveIndex(next);
  }

  const loadMore = useCallback(async () => {
    if (!nextCursor || loadingMoreRef.current) return;
    const requestId = feedRequestId.current;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    setLoadMoreError(false);
    try {
      const result = await fetchFeed({ collectionId: selected, search: deferredSearch || undefined, cursor: nextCursor });
      if (requestId !== feedRequestId.current) return;
      setItems((current) => {
        const known = new Set(current.map((item) => item.awemeId));
        return [...current, ...result.items.filter((item) => !known.has(item.awemeId))];
      });
      setNextCursor(result.nextCursor);
    } catch {
      if (requestId === feedRequestId.current) setLoadMoreError(true);
    } finally {
      loadingMoreRef.current = false;
      if (requestId === feedRequestId.current) setLoadingMore(false);
    }
  }, [deferredSearch, nextCursor, selected]);

  useEffect(() => {
    const target = paginationSentinel.current;
    const root = viewport.current;
    if (!target || !root || !nextCursor || loadMoreError || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver((entries) => {
      if (
        shouldAutoPaginate(activeIndex, items.length)
        && autoPaginatedRequestId.current !== feedRequestId.current
        && entries.some((entry) => entry.isIntersecting)
      ) {
        autoPaginatedRequestId.current = feedRequestId.current;
        void loadMore();
      }
    }, { root, rootMargin: "0px 0px 100% 0px", threshold: 0.01 });
    observer.observe(target);
    return () => observer.disconnect();
  }, [activeIndex, items.length, loadMore, loadMoreError, nextCursor]);

  function openMobileDestination(destination: MobileDestination) {
    if (destination === "collections") setDrawerOpen(true);
    else if (destination === "search") setSearchOpen(true);
    else if (destination === "activity" || destination === "settings") setUtilityPanel(destination);
    else if (destination === "feed") {
      setDrawerOpen(false);
      setUtilityPanel(null);
    }
  }

  return (
    <main data-testid="archive-feed-root" className="iphone-feed-shell flex h-[100dvh] overflow-hidden bg-[#0c0e11] text-[#f7f8fa]">
      <CollectionRail collections={collections} selected={selected} onSelect={setSelected} onOpenPanel={setUtilityPanel} />
      <section className="relative min-w-0 flex-1">
        <header className="absolute inset-x-0 top-0 z-[2] flex h-[76px] items-center justify-between border-b border-white/8 bg-[#0c0e11]/88 px-6 backdrop-blur-xl max-lg:h-auto max-lg:border-0 max-lg:bg-gradient-to-b max-lg:from-[#0c0e11]/90 max-lg:to-transparent max-lg:px-4 max-lg:pb-8 max-lg:pt-[calc(14px+env(safe-area-inset-top))]">
          <button className="flex min-h-11 items-center gap-2 text-base font-semibold lg:pointer-events-none" type="button" onClick={() => setDrawerOpen(true)}>
            <span className="hidden text-lg tracking-[-.04em] max-lg:inline">{t("brand")}</span>
            <span className="max-lg:text-sm max-lg:font-medium">{selectedName}</span>
            <CaretDown className="hidden max-lg:block" size={16} />
          </button>
          <label className="flex h-10 w-[min(34vw,380px)] items-center gap-2 rounded-lg border border-white/8 bg-white/[.04] px-3 text-[#747a84] focus-within:border-white/20 max-lg:hidden">
            <MagnifyingGlass size={19} weight="regular" />
            <input aria-label={t("searchArchive")} className="min-w-0 flex-1 bg-transparent text-sm text-white outline-none placeholder:text-[#656b75]" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("searchArchive")} />
          </label>
          <button type="button" onClick={() => setSearchOpen(true)} aria-label={t("searchArchive")} className="touch-target hidden h-11 w-11 place-items-center rounded-full border border-white/10 bg-[#111419]/55 shadow-[inset_0_1px_0_rgba(255,255,255,.08)] backdrop-blur-md active:scale-[.96] max-lg:grid"><MagnifyingGlass size={20} /></button>
        </header>

        {loading ? <FeedSkeleton label={t("loadingArchive")} /> : error ? <ErrorState label={t("feedError")} retry={t("retry")} /> : items.length === 0 ? <EmptyState title={t("emptyTitle")} body={t("emptyBody")} /> : (
          <div ref={viewport} className="feed-viewport h-[100dvh] snap-y snap-mandatory overflow-y-auto">
            {items.map((item, index) => (
              <div key={item.awemeId} data-feed-index={index}>
                <FeedCard item={item} active={index === activeIndex} onOpenDetails={setDetailItem} onOpenCollections={() => setDrawerOpen(true)} />
              </div>
            ))}
            {nextCursor || loadMoreError ? (
              <div ref={paginationSentinel} className="pagination-sentinel flex min-h-20 items-center justify-center pb-[calc(96px+env(safe-area-inset-bottom))] pt-3">
                <button type="button" disabled={loadingMore} onClick={() => void loadMore()} className="touch-target min-h-11 rounded-full border border-white/10 bg-[#15181d]/92 px-5 text-sm text-[#d8dbe0] active:scale-[.98] disabled:opacity-60">
                  {loadingMore ? t("loadingMore") : loadMoreError ? t("retryLoadMore") : t("loadMore")}
                </button>
              </div>
            ) : null}
          </div>
        )}

        {active ? (
          <aside className="absolute bottom-0 right-0 top-[76px] hidden w-[310px] border-l border-white/10 bg-[#101318]/94 px-8 py-10 xl:block">
            <p className="text-sm text-[#a8adb6]">@{active.author}</p>
            <div className="my-7 border-t border-white/8" />
            <h2 className="text-2xl font-semibold tracking-[-.03em]">{t("itemLabel")} · {active.description}</h2>
            <div className="my-7 border-t border-white/8" />
            <p className="text-sm text-[#969ba5]">{t("archived")} · {new Date(active.archivedAt * 1000).toLocaleDateString()}</p>
            <div className="my-7 border-t border-white/8" />
            <p className="text-sm text-[#969ba5]">{t("collectionLabel")} · {active.collections.map((item) => item.name).join("、")}</p>
            <div className="my-7 border-t border-white/8" />
            <p className="text-sm text-[#d7d9de]">{t("localOriginal")}</p>
          </aside>
        ) : null}

        <div className="absolute bottom-7 right-[330px] hidden grid gap-2 xl:grid">
          <button aria-label={t("previousItem")} onClick={() => move(-1)} className="grid h-11 w-11 place-items-center rounded-full border border-white/10 bg-[#15181d] active:scale-[.96]"><CaretUp size={19} /></button>
          <button aria-label={t("nextItem")} onClick={() => move(1)} className="grid h-11 w-11 place-items-center rounded-full border border-white/10 bg-[#15181d] active:scale-[.96]"><CaretDown size={19} /></button>
        </div>

        {drawerOpen ? <CollectionDrawer collections={collections} selected={selected} onSelect={(id) => { setSelected(id); setDrawerOpen(false); }} onClose={() => setDrawerOpen(false)} /> : null}
      </section>
      {utilityPanel ? <ArchiveStatusPanel kind={utilityPanel} onClose={() => setUtilityPanel(null)} /> : null}
      {searchOpen ? <MobileSearchSheet value={search} onChange={setSearch} onClose={() => setSearchOpen(false)} /> : null}
      {detailItem ? <ItemDetailsSheet item={detailItem} onClose={() => setDetailItem(null)} /> : null}
      <MobileNavigation onOpen={openMobileDestination} />
    </main>
  );
}

function CollectionDrawer({ collections, selected, onSelect, onClose }: { collections: Collection[]; selected?: string; onSelect: (id?: string) => void; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <div className="fixed inset-0 z-[7] bg-[#08090c]/50 backdrop-blur-sm" onClick={onClose}>
      <section role="dialog" aria-modal="true" aria-label={t("switchCollection")} className="absolute inset-x-0 bottom-0 rounded-t-[28px] border-t border-white/10 bg-[#181b20] px-5 pb-[calc(22px+env(safe-area-inset-bottom))] pt-3 shadow-[inset_0_1px_0_rgba(255,255,255,.08)]" onClick={(event) => event.stopPropagation()}>
        <div className="mx-auto h-1 w-11 rounded-full bg-white/25" />
        <div className="mt-5 flex items-center justify-between"><h2 className="text-lg font-semibold">{t("switchCollection")}</h2><button aria-label={t("closeDrawer")} className="grid h-11 w-11 place-items-center" onClick={onClose}><X size={20} /></button></div>
        <div className="mt-3 grid gap-1">
          {[{ id: undefined, name: t("allArchives") }, ...collections].map((item) => (
            <button key={item.id ?? "all"} onClick={() => onSelect(item.id)} className={`flex min-h-14 items-center gap-3 rounded-xl px-4 text-left text-sm ${item.id === selected ? "border-l-2 border-[#f16761] bg-white/[.08] font-semibold" : "text-[#c1c5cc]"}`}><Folders size={20} className={item.id === selected ? "text-[#f16761]" : "text-[#747a84]"} />{item.name}</button>
          ))}
        </div>
        <p className="mt-5 text-center text-xs text-[#747a84]">{t("autoSync")}</p>
      </section>
    </div>
  );
}

function FeedSkeleton({ label }: { label: string }) {
  return <div className="grid h-full place-items-center"><div className="w-[min(46dvh,420px)]"><div className="aspect-[9/16] animate-pulse rounded-xl bg-white/[.05]" /><p className="mt-4 text-center text-sm text-[#747a84]">{label}</p></div></div>;
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return <div className="grid h-full place-items-center px-6 text-center"><div><Folders className="mx-auto text-[#656b75]" size={42} weight="regular" /><h2 className="mt-5 text-xl font-semibold">{title}</h2><p className="mt-2 max-w-[38ch] text-sm leading-6 text-[#747a84]">{body}</p></div></div>;
}

function ErrorState({ label, retry }: { label: string; retry: string }) {
  return <div className="grid h-full place-items-center px-6 text-center"><div><p className="text-sm text-[#a8adb6]">{label}</p><button className="mt-5 min-h-11 rounded-lg border border-white/10 px-5 text-sm" onClick={() => window.location.reload()}>{retry}</button></div></div>;
}
