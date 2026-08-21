import { Bell, BellSlash, DownloadSimple, UserCircle, VideoCamera } from "@phosphor-icons/react";
import { useState } from "react";

import type { Creator } from "../../app/api";
import { useI18n } from "../../i18n/context";

function formatCount(value: number | null) {
  return value === null ? "—" : new Intl.NumberFormat("zh-CN", { notation: value >= 10_000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value);
}

export function CreatorProfile({ creator, refreshingIdentity = false, onArchiveAll, onToggleSubscription }: { creator: Creator; refreshingIdentity?: boolean; onArchiveAll: () => Promise<void>; onToggleSubscription: (enabled: boolean) => Promise<void> }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState<"archive" | "subscription" | null>(null);
  const subscribed = creator.subscription?.enabled ?? false;

  async function run(kind: "archive" | "subscription", action: () => Promise<void>) {
    setBusy(kind);
    try { await action(); } finally { setBusy(null); }
  }

  return (
    <section className="creator-profile" aria-label={t("creatorProfile")}>
      <div className="creator-profile-identity">
        {creator.avatarUrl ? <img src={creator.avatarUrl} alt={`${creator.nickname}${t("creatorAvatarSuffix")}`} /> : <span><UserCircle size={58} weight="duotone" /></span>}
        <div className="creator-profile-copy">
          <h1>{creator.nickname}</h1>
          <p className={`creator-douyin-id${refreshingIdentity ? " is-refreshing" : ""}`}>
            {refreshingIdentity ? t("creatorIdRefreshing") : `${t("creatorDouyinId")}${creator.uniqueId ?? t("creatorIdUnavailable")}`}
          </p>
          <p className="creator-profile-local-copy">{t("creatorLocalArchived")} {creator.archivedItemCount} / {t("creatorKnown")} {creator.knownItemCount}</p>
        </div>
      </div>
      <div className="creator-profile-stats" aria-label={t("creatorStats")}>
        <span><strong>{formatCount(creator.postCount)}</strong>{t("creatorRemotePosts")}</span>
        <span><strong>{formatCount(creator.followerCount)}</strong>{t("creatorFollowers")}</span>
        <span><strong>{creator.archivedItemCount}</strong>{t("creatorDownloadedWorks")}</span>
      </div>
      <div className="creator-profile-actions">
        <button className="friendly-button friendly-button-primary" disabled={busy !== null} onClick={() => void run("archive", onArchiveAll)}>
          <DownloadSimple size={18} />{t("archiveCreatorAll")}
        </button>
        <button className="friendly-button friendly-button-secondary" disabled={busy !== null} onClick={() => void run("subscription", () => onToggleSubscription(!subscribed))}>
          {subscribed ? <BellSlash size={18} /> : <Bell size={18} />}{t(subscribed ? "disableCreatorFollow" : "enableCreatorFollow")}
        </button>
      </div>
      <div className="creator-profile-tab" aria-current="page"><VideoCamera size={18} weight="fill" />{t("creatorCollectedWorks")}<span>{creator.knownItemCount}</span></div>
    </section>
  );
}
