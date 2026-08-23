import { Archive, BookmarkSimple, ClockCounterClockwise, DownloadSimple, FilmSlate, FolderSimple, Gear, Heart, House, Playlist, Pulse, Star, UserList } from "@phosphor-icons/react";

import type { Icon } from "@phosphor-icons/react";
import type { DashboardSnapshot, LibrarySource } from "../../app/api";
import { ProgressRing } from "../../components/ProgressRing";
import { useI18n } from "../../i18n/context";
import { sourceDownloadProgress, syncProgressState, totalDownloadProgress } from "./navigationProgress";

export type UtilityPanel = "dashboard" | "downloads" | "sync" | "activity" | "settings";

const sourceIcons: Partial<Record<LibrarySource["kind"], Icon>> = {
  post: FilmSlate,
  recommend: Star,
  like: Heart,
  favorite_video: BookmarkSimple,
  watch_history: ClockCounterClockwise,
  watch_later: Playlist,
  following: UserList,
  favorite_collection: FolderSimple,
};

const sourceTones: Partial<Record<LibrarySource["kind"], string>> = {
  post: "blue",
  recommend: "amber",
  like: "rose",
  favorite_video: "cyan",
  watch_history: "violet",
  watch_later: "amber",
  following: "green",
  favorite_collection: "blue",
};

export function CollectionRail({ sources, dashboard, selected, homeActive, onSelect, onOpenHome, onOpenPanel }: { sources: LibrarySource[]; dashboard: DashboardSnapshot | null; selected?: string; homeActive: boolean; onSelect: (id?: string) => void; onOpenHome: () => void; onOpenPanel: (panel: UtilityPanel) => void }) {
  const { t } = useI18n();
  const accountSources = sources.filter((source) => source.kind !== "favorite_collection");
  const favoriteFolders = sources.filter((source) => source.kind === "favorite_collection");
  const syncState = syncProgressState(dashboard?.health.latestSync);
  const syncLabel = t(syncState === "running" ? "syncInProgress" : syncState === "complete" ? "syncComplete" : syncState === "failed" ? "syncFailed" : "syncIdle");
  const renderSource = (source: LibrarySource) => {
    const active = source.id === selected;
    const Icon = sourceIcons[source.kind] ?? BookmarkSimple;
    const progress = sourceDownloadProgress(source, dashboard);
    return (
      <button key={source.id} type="button" aria-label={`${source.name}${source.discoveredCount}`} onClick={() => onSelect(source.id)} className={`collection-nav-item${active ? " is-active" : ""}`}>
        <span className="app-icon-well collection-nav-icon" data-icon-tone={sourceTones[source.kind] ?? "cyan"}><Icon size={18} weight="duotone" /></span>
        <span>{source.name}</span>
        <ProgressRing value={progress} compact label={`${source.name} ${t("sourceDownloadProgress")}`} />
      </button>
    );
  };
  return (
    <aside className="collection-rail friendly-panel">
      <div className="collection-brand">
        <span className="collection-brand-mark app-icon-well" data-icon-tone="cyan"><FilmSlate size={24} weight="duotone" /></span>
        <div>
          <strong>{t("brand")}</strong>
          <p>{t("brandSubtitle")}</p>
        </div>
      </div>
      <nav className="collection-navigation" aria-label={t("openCollections")}>
        <button type="button" onClick={onOpenHome} className={`collection-nav-item${homeActive ? " is-active" : ""}`}>
          <span className="app-icon-well collection-nav-icon" data-icon-tone="cyan"><House size={18} weight="duotone" /></span>
          <span>{t("home")}</span>
        </button>
        <button type="button" onClick={() => onSelect(undefined)} className={`collection-nav-item${!homeActive && selected === undefined ? " is-active" : ""}`}>
          <span className="app-icon-well collection-nav-icon" data-icon-tone="violet"><Archive size={18} weight="duotone" /></span>
          <span>{t("allArchives")}</span>
        </button>
        <p className="collection-nav-heading">{t("accountSources")}</p>
        {accountSources.map(renderSource)}
        {favoriteFolders.length ? <p className="collection-nav-heading">{t("favoriteFolders")}</p> : null}
        {favoriteFolders.map(renderSource)}
      </nav>
      <div className="collection-utility-navigation">
        <button type="button" aria-label={t("downloadJobs")} onClick={() => onOpenPanel("downloads")}><span className="app-icon-well collection-nav-icon" data-icon-tone="blue"><DownloadSimple size={18} weight="duotone" /></span><span>{t("downloadJobs")}</span><ProgressRing value={totalDownloadProgress(dashboard?.queue)} label={`${t("downloadJobs")} ${t("totalProgress")}`} /></button>
        <button type="button" aria-label={t("syncStatus")} onClick={() => onOpenPanel("sync")}><span className="app-icon-well collection-nav-icon" data-icon-tone="green"><Pulse size={18} weight="duotone" /></span><span>{t("syncStatus")}</span><ProgressRing state={syncState} label={`${t("syncStatus")} ${syncLabel}`} /></button>
      </div>
      <button type="button" onClick={() => onOpenPanel("settings")} className="collection-settings"><span className="app-icon-well collection-nav-icon" data-icon-tone="amber"><Gear size={18} weight="duotone" /></span><span>{t("settings")}</span></button>
      <div className="collection-connection"><span className="app-icon-well collection-connection-icon" data-icon-tone="green"><Archive size={15} weight="duotone" /></span><span>{t("connected")} · {t("autoSync")}</span></div>
    </aside>
  );
}
