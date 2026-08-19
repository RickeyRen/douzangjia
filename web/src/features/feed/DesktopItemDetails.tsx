import {
  Archive,
  CalendarBlank,
  FolderSimple,
  HardDrives,
  NotePencil,
  UserCircle,
} from "@phosphor-icons/react";

import type { FeedItem } from "../../app/api";
import { useI18n } from "../../i18n/context";

export function DesktopItemDetails({ item }: { item: FeedItem }) {
  const { t } = useI18n();
  const rows = [
    {
      icon: <UserCircle size={20} weight="duotone" />,
      label: t("source"),
      value: `@${item.author}`,
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
      <div className="desktop-local-state">
        <HardDrives size={22} weight="duotone" />
        <div>
          <strong>{t("permanentRetention")}</strong>
          <p>{t("permanentRetentionBody")}</p>
        </div>
      </div>
    </aside>
  );
}
