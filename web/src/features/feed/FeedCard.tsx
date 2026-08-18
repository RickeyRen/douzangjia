import { FolderSimple, Info, Play, SpeakerHigh, SpeakerSlash } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

import type { FeedItem } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { GalleryViewer } from "./GalleryViewer";

export function FeedCard({ item, active, onOpenDetails, onOpenCollections }: { item: FeedItem; active: boolean; onOpenDetails?: (item: FeedItem) => void; onOpenCollections?: () => void }) {
  const { t } = useI18n();
  const collection = item.collections[0]?.name ?? t("allArchives");
  const video = useRef<HTMLVideoElement>(null);
  const [playing, setPlaying] = useState(active);
  const [muted, setMuted] = useState(true);
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const element = video.current;
    if (!element) return;
    if (!active) {
      element.pause();
      setPlaying(false);
      return;
    }
    void element.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  }, [active]);

  function togglePlayback() {
    const element = video.current;
    if (!element) return;
    if (playing) {
      element.pause();
      setPlaying(false);
    } else {
      void element.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
    }
  }

  function updateProgress() {
    const element = video.current;
    setProgress(element && Number.isFinite(element.duration) && element.duration > 0 ? element.currentTime / element.duration : 0);
  }
  return (
    <article className="feed-card relative grid min-h-[100dvh] snap-start snap-always place-items-center bg-[#0c0e11]" data-testid={active ? "feed-card-active" : "feed-card"}>
      <div className="media-frame relative h-[min(82dvh,860px)] w-[min(46.125dvh,484px)] overflow-hidden rounded-xl bg-[#15181d] shadow-[0_24px_70px_rgba(0,0,0,.28)] max-lg:h-[100dvh] max-lg:w-full max-lg:rounded-none">
        {item.media.length === 0 ? (
          <div className="grid h-full place-items-center px-8 text-center text-sm text-[#747a84]">{t("noMedia")}</div>
        ) : item.type === "gallery" ? (
          <GalleryViewer media={item.media} description={item.description} />
        ) : (
          <>
            <video ref={video} className="h-full w-full object-contain" src={item.media[0].url} muted={muted} loop playsInline preload={active ? "metadata" : "none"} onTimeUpdate={updateProgress} onLoadedMetadata={updateProgress} />
            <button type="button" onClick={togglePlayback} aria-label={playing ? t("pauseVideo") : t("playVideo")} className="absolute inset-0 z-[1] grid place-items-center outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#f16761]">
              {!playing ? <span className="grid h-16 w-16 place-items-center rounded-full border border-white/15 bg-[#101216]/70 shadow-[inset_0_1px_0_rgba(255,255,255,.1)] backdrop-blur-md"><Play size={28} weight="fill" /></span> : null}
            </button>
          </>
        )}

        <div className="pointer-events-none absolute inset-x-0 bottom-0 hidden bg-gradient-to-t from-[#0c0e11]/95 via-[#0c0e11]/45 to-transparent pb-[calc(84px+env(safe-area-inset-bottom))] pl-5 pr-24 pt-32 max-lg:block">
          <p className="text-base font-semibold">@{item.author}</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-.025em]">{item.description}</h2>
          <p className="mt-3 text-sm text-white/65">{t("from")} {collection} · {t("localOriginal")}</p>
        </div>

        <div className="mobile-media-actions absolute bottom-48 right-3 z-[2] hidden grid gap-3 max-lg:grid">
          {item.type === "video" && item.media.length > 0 ? <MediaAction label={muted ? t("soundOn") : t("muteVideo")} onClick={() => setMuted((current) => !current)} icon={muted ? <SpeakerSlash size={22} /> : <SpeakerHigh size={22} />} /> : null}
          <MediaAction label={t("showCollections")} onClick={onOpenCollections} icon={<FolderSimple size={22} />} />
          <MediaAction label={t("itemInformation")} onClick={() => onOpenDetails?.(item)} icon={<Info size={22} />} />
        </div>
        {item.type === "video" && item.media.length > 0 ? <div className="absolute inset-x-5 bottom-[calc(86px+env(safe-area-inset-bottom))] z-[2] hidden max-lg:block"><progress aria-label={t("videoProgress")} className="media-progress h-1 w-full" max={1} value={progress} /></div> : null}
      </div>
    </article>
  );
}

function MediaAction({ label, onClick, icon }: { label: string; onClick?: () => void; icon: React.ReactNode }) {
  return <button type="button" onClick={onClick} aria-label={label} className="touch-target grid w-16 justify-items-center gap-1 rounded-xl py-1 text-[11px] text-white/90 active:scale-[.96]"><span className="grid h-11 w-11 place-items-center rounded-full border border-white/10 bg-[#101216]/72 shadow-[inset_0_1px_0_rgba(255,255,255,.08)] backdrop-blur-md">{icon}</span><span>{label}</span></button>;
}
