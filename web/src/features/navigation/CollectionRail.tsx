import { Archive, DownloadSimple, FilmSlate, FolderSimple, Gear, House, Pulse } from "@phosphor-icons/react";

import type { Collection } from "../../app/api";
import { useI18n } from "../../i18n/context";

export type UtilityPanel = "downloads" | "sync" | "activity" | "settings";

export function CollectionRail({ collections, selected, onSelect, onOpenPanel }: { collections: Collection[]; selected?: string; onSelect: (id?: string) => void; onOpenPanel: (panel: UtilityPanel) => void }) {
  const { t } = useI18n();
  const items = [{ id: undefined, name: t("allArchives"), icon: House }, ...collections.map((collection) => ({ ...collection, icon: FolderSimple }))];
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
        {items.map(({ id, name, icon: Icon }) => {
          const active = id === selected;
          const itemCount = collections.find((item) => item.id === id)?.itemCount;
          return (
            <button key={id ?? "all"} type="button" onClick={() => onSelect(id)} className={`collection-nav-item${active ? " is-active" : ""}`}>
              <Icon size={21} weight={active ? "fill" : "regular"} />
              <span>{name}</span>
              {itemCount !== undefined ? <small>{itemCount}</small> : null}
            </button>
          );
        })}
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
