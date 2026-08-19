import { Archive, BookmarkSimple, ClockCounterClockwise, DownloadSimple, FilmSlate, FolderSimple, Gear, Heart, House, Playlist, Pulse, UserList } from "@phosphor-icons/react";

import type { Icon } from "@phosphor-icons/react";
import type { LibrarySource } from "../../app/api";
import { useI18n } from "../../i18n/context";

export type UtilityPanel = "downloads" | "sync" | "activity" | "settings";

const sourceIcons: Partial<Record<LibrarySource["kind"], Icon>> = {
  post: FilmSlate,
  like: Heart,
  favorite_video: BookmarkSimple,
  watch_history: ClockCounterClockwise,
  watch_later: Playlist,
  following: UserList,
  favorite_collection: FolderSimple,
};

export function CollectionRail({ sources, selected, onSelect, onOpenPanel }: { sources: LibrarySource[]; selected?: string; onSelect: (id?: string) => void; onOpenPanel: (panel: UtilityPanel) => void }) {
  const { t } = useI18n();
  const accountSources = sources.filter((source) => source.kind !== "favorite_collection");
  const favoriteFolders = sources.filter((source) => source.kind === "favorite_collection");
  const renderSource = (source: LibrarySource) => {
    const active = source.id === selected;
    const Icon = sourceIcons[source.kind] ?? BookmarkSimple;
    return (
      <button key={source.id} type="button" onClick={() => onSelect(source.id)} className={`collection-nav-item${active ? " is-active" : ""}`}>
        <Icon size={21} weight={active ? "fill" : "regular"} />
        <span>{source.name}</span>
        <small>{source.discoveredCount}</small>
      </button>
    );
  };
  return (
    <aside className="collection-rail friendly-panel">
      <div className="collection-brand">
        <span className="collection-brand-mark"><FilmSlate size={27} weight="fill" /></span>
        <div>
          <strong>{t("brand")}</strong>
          <p>{t("brandSubtitle")}</p>
        </div>
      </div>
      <nav className="collection-navigation" aria-label={t("openCollections")}>
        <button type="button" onClick={() => onSelect(undefined)} className={`collection-nav-item${selected === undefined ? " is-active" : ""}`}>
          <House size={21} weight={selected === undefined ? "fill" : "regular"} />
          <span>{t("allArchives")}</span>
        </button>
        <p className="collection-nav-heading">{t("accountSources")}</p>
        {accountSources.map(renderSource)}
        {favoriteFolders.length ? <p className="collection-nav-heading">{t("favoriteFolders")}</p> : null}
        {favoriteFolders.map(renderSource)}
      </nav>
      <div className="collection-utility-navigation">
        <button type="button" onClick={() => onOpenPanel("downloads")}><DownloadSimple size={21} weight="duotone" /><span>{t("downloadJobs")}</span></button>
        <button type="button" onClick={() => onOpenPanel("sync")}><Pulse size={21} weight="duotone" /><span>{t("syncStatus")}</span></button>
      </div>
      <button type="button" onClick={() => onOpenPanel("settings")} className="collection-settings"><Gear size={21} weight="duotone" /><span>{t("settings")}</span></button>
      <div className="collection-connection"><Archive size={17} weight="duotone" /><span>{t("connected")} · {t("autoSync")}</span></div>
    </aside>
  );
}
