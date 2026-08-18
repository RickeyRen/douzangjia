import { Archive, FolderSimple, Info } from "@phosphor-icons/react";

import type { FeedItem } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { GalleryViewer } from "./GalleryViewer";

export function FeedCard({ item, active }: { item: FeedItem; active: boolean }) {
  const { t } = useI18n();
  const collection = item.collections[0]?.name ?? t("allArchives");
  return (
    <article className="feed-card relative grid min-h-[100dvh] snap-start snap-always place-items-center bg-[#0c0e11]" data-testid={active ? "feed-card-active" : "feed-card"}>
      <div className="media-frame relative h-[min(82dvh,860px)] w-[min(46.125dvh,484px)] overflow-hidden rounded-xl bg-[#15181d] shadow-[0_24px_70px_rgba(0,0,0,.28)] max-md:h-[100dvh] max-md:w-full max-md:rounded-none">
        {item.media.length === 0 ? (
          <div className="grid h-full place-items-center px-8 text-center text-sm text-[#747a84]">{t("noMedia")}</div>
        ) : item.type === "gallery" ? (
          <GalleryViewer media={item.media} description={item.description} />
        ) : (
          <video className="h-full w-full object-contain" src={item.media[0].url} autoPlay={active} muted loop playsInline preload={active ? "metadata" : "none"} />
        )}

        <div className="pointer-events-none absolute inset-x-0 bottom-0 hidden bg-gradient-to-t from-[#0c0e11]/95 via-[#0c0e11]/45 to-transparent px-5 pb-[calc(84px+env(safe-area-inset-bottom))] pt-32 max-md:block">
          <p className="text-base font-semibold">@{item.author}</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-.025em]">{item.description}</h2>
          <p className="mt-3 text-sm text-white/65">{t("from")} {collection} · {t("localOriginal")}</p>
        </div>

        <div className="absolute bottom-32 right-3 hidden grid gap-4 max-md:grid">
          {[
            [Archive, t("archived")],
            [FolderSimple, t("source")],
            [Info, t("information")],
          ].map(([Icon, label]) => (
            <div key={String(label)} className="grid w-14 justify-items-center gap-1 text-[11px] text-white/90">
              <span className="grid h-11 w-11 place-items-center rounded-full border border-white/10 bg-[#101216]/70 backdrop-blur-md"><Icon size={22} weight="regular" /></span>
              {String(label)}
            </div>
          ))}
        </div>
      </div>
    </article>
  );
}
