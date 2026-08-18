import { Archive, DownloadSimple, FolderSimple, Gear, House, Pulse } from "@phosphor-icons/react";

import type { Collection } from "../../app/api";
import { useI18n } from "../../i18n/context";

export type UtilityPanel = "downloads" | "sync" | "settings";

export function CollectionRail({ collections, selected, onSelect, onOpenPanel }: { collections: Collection[]; selected?: string; onSelect: (id?: string) => void; onOpenPanel: (panel: UtilityPanel) => void }) {
  const { t } = useI18n();
  const items = [{ id: undefined, name: t("allArchives"), icon: House }, ...collections.map((collection) => ({ ...collection, icon: FolderSimple }))];
  return (
    <aside className="hidden h-[100dvh] w-[230px] shrink-0 border-r border-white/10 bg-[#101318] px-4 py-7 lg:flex lg:flex-col">
      <div className="px-3">
        <strong className="text-2xl font-semibold tracking-[-.04em]">{t("brand")}</strong>
        <p className="mt-1 text-xs text-[#747a84]">{t("brandSubtitle")}</p>
      </div>
      <nav className="mt-12 grid gap-1" aria-label={t("openCollections")}>
        {items.map(({ id, name, icon: Icon }) => {
          const active = id === selected;
          return (
            <button key={id ?? "all"} type="button" onClick={() => onSelect(id)} className={`group relative flex min-h-12 items-center gap-3 rounded-lg px-3 text-left text-sm transition-colors active:scale-[.98] ${active ? "bg-white/[.08] text-white" : "text-[#a8adb6] hover:bg-white/[.04] hover:text-white"}`}>
              {active ? <span className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-[#f16761]" /> : null}
              <Icon size={20} weight="regular" />
              <span className="min-w-0 flex-1 truncate">{name}</span>
              {"itemCount" in (collections.find((item) => item.id === id) ?? {}) ? <span className="text-xs text-[#686e78]">{collections.find((item) => item.id === id)?.itemCount}</span> : null}
            </button>
          );
        })}
      </nav>
      <div className="my-5 border-t border-white/8" />
      <button type="button" onClick={() => onOpenPanel("downloads")} className="flex min-h-11 items-center gap-3 px-3 text-sm text-[#969ba5] transition-colors hover:text-white"><DownloadSimple size={20} />{t("downloadJobs")}</button>
      <button type="button" onClick={() => onOpenPanel("sync")} className="flex min-h-11 items-center gap-3 px-3 text-sm text-[#969ba5] transition-colors hover:text-white"><Pulse size={20} />{t("syncStatus")}</button>
      <button type="button" onClick={() => onOpenPanel("settings")} className="mt-auto flex min-h-11 items-center gap-3 border-t border-white/8 px-3 pt-5 text-sm text-[#969ba5] transition-colors hover:text-white"><Gear size={20} />{t("settings")}</button>
      <div className="mt-4 flex items-center gap-2 px-3 text-xs text-[#747a84]"><Archive size={15} /><span>{t("connected")} · {t("autoSync")}</span></div>
    </aside>
  );
}
