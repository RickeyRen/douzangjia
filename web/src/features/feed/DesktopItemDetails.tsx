import {
  Archive,
  CalendarBlank,
  FolderSimple,
  HardDrives,
  IdentificationCard,
  NotePencil,
  UserCircle,
} from "@phosphor-icons/react";

import type { FeedItem } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { AuthorButton } from "./AuthorButton";
import { LocalStateBadge } from "./LocalStateBadge";
import { RichItemDetails } from "./RichItemDetails";

export function DesktopItemDetails({ item, onOpenAuthor, refreshingIdentity = false }: { item: FeedItem; onOpenAuthor?: (creatorId: string | null, author: string) => void; refreshingIdentity?: boolean }) {
  const { t } = useI18n();
  const rows = [
    {
      icon: <UserCircle size={20} weight="duotone" />,
      label: t("source"),
      value: <AuthorButton creatorId={item.creatorId} author={item.author} onOpen={onOpenAuthor} />,
    },
    {
      icon: <IdentificationCard size={20} weight="duotone" />,
      label: t("itemCreatorDouyinId"),
      value: item.creator?.uniqueId || (refreshingIdentity ? t("creatorIdRefreshing") : t("creatorIdUnavailable")),
    },
    {
      icon: <NotePencil size={20} weight="duotone" />,
      label: t("information"),
      value: item.description,
    },
    {
      icon: <CalendarBlank size={20} weight="duotone" />,
      label: t("archived"),
      value: new Date(item.archivedAt * 1000).toLocaleDateString(),
    },
    {
      icon: <FolderSimple size={20} weight="duotone" />,
      label: t("collectionLabel"),
      value:
        item.collections.map((collection) => collection.name).join("、") ||
        t("allArchives"),
    },
  ];

  return (
    <aside
      data-testid="desktop-details"
      className="desktop-item-details friendly-panel"
      aria-label={t("itemInformation")}
    >
      <header className="desktop-details-header">
        <span className="desktop-details-mark">
          <Archive size={22} weight="duotone" />
        </span>
        <div>
          <p>{t("itemInformation")}</p>
          <strong>{t("localOriginal")}</strong>
        </div>
      </header>
      <dl className="desktop-details-list">
        {rows.map((row) => (
          <div key={row.label} className="desktop-details-row">
            <dt>
              <span>{row.icon}</span>
              {row.label}
            </dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
      <RichItemDetails item={item} />
      <div className="desktop-local-state">
        <HardDrives size={22} weight="duotone" />
        <div>
          <LocalStateBadge local={item.local} detailed />
          <p>{t("permanentRetentionBody")}</p>
        </div>
      </div>
    </aside>
  );
}
