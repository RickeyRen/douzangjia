import { CaretDown, CaretUp, Folders, MagnifyingGlass, X } from "@phosphor-icons/react";
import { useDeferredValue, useEffect, useRef, useState } from "react";

import { fetchCollections, fetchFeed, type Collection, type FeedItem } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { CollectionRail } from "../navigation/CollectionRail";
import type { UtilityPanel } from "../navigation/CollectionRail";
import { ArchiveStatusPanel } from "../status/ArchiveStatusPanel";
import { FeedCard } from "./FeedCard";

export function feedIndexFromTarget(target: HTMLElement): number {
  const index = Number(target.dataset.feedIndex);
  return Number.isInteger(index) && index >= 0 ? index : 0;
}

export function FeedPage() {
  const { t } = useI18n();
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selected, setSelected] = useState<string | undefined>();
  const [items, setItems] = useState<FeedItem[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [utilityPanel, setUtilityPanel] = useState<UtilityPanel | null>(null);
  const viewport = useRef<HTMLDivElement>(null);

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
    setLoading(true);
    setError(false);
    void fetchFeed({ collectionId: selected, search: deferredSearch || undefined })
      .then((result) => {
        if (!cancelled) {
          setItems(result.items);
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

  return (
    <main className="flex h-[100dvh] overflow-hidden bg-[#0c0e11] text-[#f7f8fa]">
      <CollectionRail collections={collections} selected={selected} onSelect={setSelected} onOpenPanel={setUtilityPanel} />
      <section className="relative min-w-0 flex-1">
        <header className="absolute inset-x-0 top-0 z-[2] flex h-[76px] items-center justify-between border-b border-white/8 bg-[#0c0e11]/88 px-6 backdrop-blur-xl max-md:h-auto max-md:border-0 max-md:bg-gradient-to-b max-md:from-[#0c0e11]/90 max-md:to-transparent max-md:px-4 max-md:pb-8 max-md:pt-[calc(14px+env(safe-area-inset-top))]">
          <button className="flex min-h-11 items-center gap-2 text-base font-semibold lg:pointer-events-none" type="button" onClick={() => setDrawerOpen(true)}>
            <span className="hidden text-lg tracking-[-.04em] max-md:inline">{t("brand")}</span>
            <span className="max-md:text-sm max-md:font-medium">{selectedName}</span>
            <CaretDown className="hidden max-md:block" size={16} />
          </button>
          <label className="flex h-10 w-[min(34vw,380px)] items-center gap-2 rounded-lg border border-white/8 bg-white/[.04] px-3 text-[#747a84] focus-within:border-white/20 max-md:w-11 max-md:justify-center max-md:border-0 max-md:bg-transparent max-md:px-0">
            <MagnifyingGlass size={19} weight="regular" />
            <input className="min-w-0 flex-1 bg-transparent text-sm text-white outline-none placeholder:text-[#656b75] max-md:hidden" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("searchArchive")} />
          </label>
        </header>

        {loading ? <FeedSkeleton label={t("loadingArchive")} /> : error ? <ErrorState label={t("feedError")} retry={t("retry")} /> : items.length === 0 ? <EmptyState title={t("emptyTitle")} body={t("emptyBody")} /> : (
          <div ref={viewport} className="feed-viewport h-[100dvh] snap-y snap-mandatory overflow-y-auto">
            {items.map((item, index) => (
              <div key={item.awemeId} data-feed-index={index}>
                <FeedCard item={item} active={index === activeIndex} />
              </div>
            ))}
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

        <button type="button" onClick={() => setDrawerOpen(true)} className="absolute inset-x-4 bottom-[calc(12px+env(safe-area-inset-bottom))] z-[2] hidden min-h-12 items-center justify-center gap-2 rounded-xl border border-white/10 bg-[#15181d]/92 text-sm font-medium shadow-[inset_0_1px_0_rgba(255,255,255,.08)] backdrop-blur-xl max-md:flex">
          <Folders size={20} weight="regular" />{t("switchCollection")}
        </button>

        {drawerOpen ? <CollectionDrawer collections={collections} selected={selected} onSelect={(id) => { setSelected(id); setDrawerOpen(false); }} onClose={() => setDrawerOpen(false)} /> : null}
      </section>
      {utilityPanel ? <ArchiveStatusPanel kind={utilityPanel} onClose={() => setUtilityPanel(null)} /> : null}
    </main>
  );
}

function CollectionDrawer({ collections, selected, onSelect, onClose }: { collections: Collection[]; selected?: string; onSelect: (id?: string) => void; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <div className="fixed inset-0 z-[3] bg-[#08090c]/50 backdrop-blur-sm" onClick={onClose}>
      <section className="absolute inset-x-0 bottom-0 rounded-t-[28px] border-t border-white/10 bg-[#181b20] px-5 pb-[calc(22px+env(safe-area-inset-bottom))] pt-3 shadow-[inset_0_1px_0_rgba(255,255,255,.08)]" onClick={(event) => event.stopPropagation()}>
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
