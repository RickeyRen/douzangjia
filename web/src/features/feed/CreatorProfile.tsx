import { Bell, BellSlash, DownloadSimple, UserCircle } from "@phosphor-icons/react";
import { useState } from "react";

import type { Creator } from "../../app/api";
import { useI18n } from "../../i18n/context";

export function CreatorProfile({ creator, onArchiveAll, onToggleSubscription }: { creator: Creator; onArchiveAll: () => Promise<void>; onToggleSubscription: (enabled: boolean) => Promise<void> }) {
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
        {creator.avatarUrl ? <img src={creator.avatarUrl} alt="" /> : <span><UserCircle size={32} weight="duotone" /></span>}
        <div><strong>@{creator.nickname}</strong>{creator.uniqueId ? <small>{creator.uniqueId}</small> : null}</div>
      </div>
      <div className="creator-profile-stats">
        <span><strong>{creator.postCount ?? "—"}</strong>{t("creatorRemotePosts")}</span>
        <span><strong>{creator.followerCount ?? "—"}</strong>{t("creatorFollowers")}</span>
        <span><strong>{creator.archivedItemCount} / {creator.knownItemCount}</strong>{t("creatorLocalStatus")}</span>
      </div>
      <p className="creator-profile-local-copy">{t("creatorLocalArchived")} {creator.archivedItemCount} / {t("creatorKnown")} {creator.knownItemCount}</p>
      <div className="creator-profile-actions">
        <button className="friendly-button friendly-button-primary" disabled={busy !== null} onClick={() => void run("archive", onArchiveAll)}>
          <DownloadSimple size={18} />{t("archiveCreatorAll")}
        </button>
        <button className="friendly-button friendly-button-secondary" disabled={busy !== null} onClick={() => void run("subscription", () => onToggleSubscription(!subscribed))}>
          {subscribed ? <BellSlash size={18} /> : <Bell size={18} />}{t(subscribed ? "disableCreatorFollow" : "enableCreatorFollow")}
        </button>
      </div>
    </section>
  );
}
