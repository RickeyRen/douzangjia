import { Archive, FolderSimple, HardDrives, IdentificationCard, X } from "@phosphor-icons/react";

import type { FeedItem } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { AuthorButton } from "./AuthorButton";
import { LocalStateBadge } from "./LocalStateBadge";
import { RichItemDetails } from "./RichItemDetails";

export function ItemDetailsSheet({ item, onClose, onOpenAuthor, refreshingIdentity = false }: { item: FeedItem; onClose: () => void; onOpenAuthor?: (creatorId: string | null, author: string) => void; refreshingIdentity?: boolean }) {
  const { t } = useI18n();
  return (
    <div className="collection-drawer-overlay" onClick={onClose}>
      <section role="dialog" aria-modal="true" aria-label={t("itemInformation")} className="item-details-drawer" onClick={(event) => event.stopPropagation()}>
        <div className="drawer-handle" />
        <header className="item-details-header">
          <div><p><AuthorButton creatorId={item.creatorId} author={item.author} onOpen={onOpenAuthor} /></p><h2>{t("itemInformation")}</h2></div>
          <button type="button" onClick={onClose} aria-label={t("closePanel")} className="touch-target utility-close-button"><X size={20} /></button>
        </header>
        <p className="item-details-description">{item.description}</p>
        <dl className="item-details-list">
          <DetailRow icon={<IdentificationCard size={20} />} label={t("itemCreatorDouyinId")} value={item.creator?.uniqueId || (refreshingIdentity ? t("creatorIdRefreshing") : t("creatorIdUnavailable"))} />
          <DetailRow icon={<Archive size={20} />} label={t("archived")} value={new Date(item.archivedAt * 1000).toLocaleDateString()} />
          <DetailRow icon={<FolderSimple size={20} />} label={t("collectionLabel")} value={item.collections.map((entry) => entry.name).join("、") || t("allArchives")} />
          <DetailRow icon={<HardDrives size={20} />} label={t("source")} value={t("localOriginal")} />
        </dl>
        <RichItemDetails item={item} />
        <LocalStateBadge local={item.local} detailed />
      </section>
    </div>
  );
}

function DetailRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return <div className="item-detail-row"><span>{icon}</span><dt>{label}</dt><dd>{value}</dd></div>;
}
