import { Archive, FolderSimple, HardDrives, X } from "@phosphor-icons/react";

import type { FeedItem } from "../../app/api";
import { useI18n } from "../../i18n/context";

export function ItemDetailsSheet({ item, onClose }: { item: FeedItem; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <div className="fixed inset-0 z-[8] bg-[#08090c]/55 backdrop-blur-sm" onClick={onClose}>
      <section role="dialog" aria-modal="true" aria-label={t("itemInformation")} className="absolute inset-x-0 bottom-0 max-h-[78dvh] overflow-y-auto rounded-t-[28px] border-t border-white/10 bg-[#171a1f] px-5 pb-[calc(24px+env(safe-area-inset-bottom))] pt-3 shadow-[inset_0_1px_0_rgba(255,255,255,.08)] md:left-auto md:top-0 md:w-[430px] md:rounded-none md:border-l md:border-t-0 md:pt-5" onClick={(event) => event.stopPropagation()}>
        <div className="mx-auto h-1 w-11 rounded-full bg-white/25 md:hidden" />
        <header className="mt-3 flex min-h-12 items-center justify-between border-b border-white/8 pb-3">
          <div><p className="text-xs text-[#8d939d]">@{item.author}</p><h2 className="mt-1 text-lg font-semibold">{t("itemInformation")}</h2></div>
          <button type="button" onClick={onClose} aria-label={t("closePanel")} className="touch-target grid h-11 w-11 place-items-center rounded-full active:scale-[.96]"><X size={20} /></button>
        </header>
        <p className="py-5 text-xl font-semibold leading-8 tracking-[-.02em]">{item.description}</p>
        <dl className="divide-y divide-white/8 border-y border-white/8">
          <DetailRow icon={<Archive size={20} />} label={t("archived")} value={new Date(item.archivedAt * 1000).toLocaleDateString()} />
          <DetailRow icon={<FolderSimple size={20} />} label={t("collectionLabel")} value={item.collections.map((entry) => entry.name).join("、") || t("allArchives")} />
          <DetailRow icon={<HardDrives size={20} />} label={t("source")} value={t("localOriginal")} />
        </dl>
      </section>
    </div>
  );
}

function DetailRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return <div className="grid grid-cols-[28px_92px_1fr] items-start gap-2 py-4 text-sm"><span className="text-[#f16761]">{icon}</span><dt className="text-[#858b95]">{label}</dt><dd className="m-0 text-right text-[#e2e4e8]">{value}</dd></div>;
}
