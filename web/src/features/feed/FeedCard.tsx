import { DownloadSimple, FolderSimple, Info, Pause, Play, SpeakerHigh, SpeakerSlash } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

import type { FeedItem } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { AuthorButton } from "./AuthorButton";
import { GalleryViewer } from "./GalleryViewer";
import { LocalStateBadge } from "./LocalStateBadge";

export function FeedCard({ item, active, onOpenDetails, onOpenCollections, onOpenAuthor, onArchiveItem }: { item: FeedItem; active: boolean; onOpenDetails?: (item: FeedItem) => void; onOpenCollections?: () => void; onOpenAuthor?: (creatorId: string | null, author: string) => void; onArchiveItem?: (item: FeedItem) => void }) {
  const { t } = useI18n();
  const collection = item.collections[0]?.name ?? t("allArchives");
  const titleId = `feed-title-${item.awemeId}`;
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
    <article aria-labelledby={titleId} className="feed-card archive-media-stage snap-start snap-always" data-testid={active ? "feed-card-active" : "feed-card"}>
      <div className="media-frame archive-media-frame">
        {item.media.length === 0 ? (
          <div className="archive-media-empty">{t("noMedia")}</div>
        ) : item.type === "gallery" ? (
          <GalleryViewer media={item.media} description={item.description} />
        ) : (
          <>
            <video ref={video} className="archive-media-element" src={item.media[0].url} muted={muted} loop playsInline preload={active ? "metadata" : "none"} onTimeUpdate={updateProgress} onLoadedMetadata={updateProgress} />
            <button type="button" onClick={togglePlayback} aria-label={playing ? t("pauseVideo") : t("playVideo")} className={`archive-playback-hitarea${playing ? " is-playing" : ""}`}>
              <span className="archive-playback-icon">{playing ? <Pause size={24} weight="fill" /> : <Play size={27} weight="fill" />}</span>
            </button>
          </>
        )}

        <div className="mobile-media-caption">
          <p className="mobile-media-author"><AuthorButton creatorId={item.creatorId} author={item.author} onOpen={onOpenAuthor} /></p>
          <h2 id={titleId}>{item.description}</h2>
          <p className="mobile-media-source">{t("from")} {collection} · {t("localOriginal")}</p>
          <LocalStateBadge local={item.local} />
        </div>

        <div role="toolbar" aria-label={t("mediaControls")} className="mobile-media-actions media-control-toolbar">
          {item.type === "video" && item.media.length > 0 ? <MediaAction label={muted ? t("soundOn") : t("muteVideo")} onClick={() => setMuted((current) => !current)} icon={muted ? <SpeakerSlash size={22} /> : <SpeakerHigh size={22} />} /> : null}
          <MediaAction label={t("saveToNas")} onClick={() => onArchiveItem?.(item)} icon={<DownloadSimple size={22} />} />
          <MediaAction label={t("showCollections")} onClick={onOpenCollections} icon={<FolderSimple size={22} />} />
          <MediaAction label={t("itemInformation")} onClick={() => onOpenDetails?.(item)} icon={<Info size={22} />} />
        </div>
        {item.type === "video" && item.media.length > 0 ? <div className="mobile-media-progress"><progress aria-label={t("videoProgress")} className="media-progress" max={1} value={progress} /></div> : null}
      </div>
    </article>
  );
}

function MediaAction({ label, onClick, icon }: { label: string; onClick?: () => void; icon: React.ReactNode }) {
  return <button type="button" onClick={onClick} aria-label={label} className="touch-target media-action"><span className="media-action-icon">{icon}</span><span>{label}</span></button>;
}
