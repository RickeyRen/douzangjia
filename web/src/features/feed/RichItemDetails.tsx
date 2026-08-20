import { ArrowClockwise, ChartBar, FileVideo, GlobeHemisphereWest } from "@phosphor-icons/react";
import { useState } from "react";

import { checkRemoteAvailability, type FeedItem, type RemoteAvailability } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { formatBytes } from "../status/downloadFormat";

const numberFormat = new Intl.NumberFormat("zh-CN");

function durationLabel(durationMs: number | null | undefined): string {
  if (!durationMs) return "—";
  const totalSeconds = Math.round(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

function remoteLabel(status: RemoteAvailability["status"], t: ReturnType<typeof useI18n>["t"]): string {
  return {
    available: t("remoteAvailable"),
    deleted: t("remoteDeleted"),
    private: t("remotePrivate"),
    restricted: t("remoteRestricted"),
    auth_required: t("remoteAuthRequired"),
    rate_limited: t("remoteRateLimited"),
    unknown: t("remoteUnknown"),
  }[status];
}

export function RichItemDetails({ item }: { item: FeedItem }) {
  const { t } = useI18n();
  const [remote, setRemote] = useState<RemoteAvailability>(
    item.remoteAvailability ?? { status: "unknown", checkedAt: null, evidenceCode: null, lastAvailableAt: null },
  );
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState(false);
  const statistics = item.douyin?.statistics ?? {};
  const statisticEntries = [
    [t("playCount"), statistics.playCount],
    [t("likeCount"), statistics.diggCount],
    [t("commentCount"), statistics.commentCount],
    [t("collectCount"), statistics.collectCount],
    [t("shareCount"), statistics.shareCount],
  ].filter((entry): entry is [string, number] => typeof entry[1] === "number");

  async function refreshRemote() {
    setChecking(true);
    setCheckError(false);
    try {
      setRemote(await checkRemoteAvailability(item.awemeId));
    } catch {
      setCheckError(true);
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="rich-item-details">
      <section className="rich-detail-section">
        <header><GlobeHemisphereWest size={18} weight="duotone" /><h3>{t("remoteStatus")}</h3></header>
        <div className={`remote-availability is-${remote.status}`}><i />{remoteLabel(remote.status, t)}</div>
        <button type="button" className="rich-detail-action" disabled={checking} onClick={() => void refreshRemote()} aria-label={checking ? t("checkingRemote") : t("recheckRemote")}>
          <ArrowClockwise className={checking ? "is-spinning" : ""} size={16} />
          {checking ? t("checkingRemote") : t("recheckRemote")}
        </button>
        {checkError ? <p className="rich-detail-error">{t("remoteCheckFailed")}</p> : null}
      </section>

      <section className="rich-detail-section">
        <header><ChartBar size={18} weight="duotone" /><h3>{t("douyinData")}</h3></header>
        {statisticEntries.length ? <dl className="douyin-stat-grid">{statisticEntries.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{numberFormat.format(value)}</dd></div>)}</dl> : null}
        <dl className="rich-detail-lines">
          <div><dt>{t("duration")}</dt><dd>{durationLabel(item.douyin?.durationMs)}</dd></div>
          {item.douyin?.hashtags.length ? <div><dt>{t("hashtags")}</dt><dd>{item.douyin.hashtags.map((tag) => `#${tag}`).join(" ")}</dd></div> : null}
        </dl>
      </section>

      {item.media.map((media) => {
        const technical = media.technical;
        return (
          <section key={media.id} className="rich-detail-section rich-file-section">
            <header><FileVideo size={18} weight="duotone" /><h3>{t("fileDetails")} {media.index + 1}</h3></header>
            <dl className="rich-detail-lines">
              <div><dt>{t("fileSize")}</dt><dd>{formatBytes(media.byteSize ?? 0)}</dd></div>
              <div><dt>{t("resolution")}</dt><dd>{technical?.width && technical.height ? `${technical.width} × ${technical.height}` : "—"}</dd></div>
              <div><dt>{t("encoding")}</dt><dd>{technical?.codec ? `${technical.codec}${technical.fps ? ` · ${technical.fps} fps` : ""}` : t("probeUnavailable")}</dd></div>
              <div><dt>{t("bitRate")}</dt><dd>{technical?.bitRate ? `${(technical.bitRate / 1_000_000).toFixed(1)} Mbps` : "—"}</dd></div>
              {media.relativePath ? <div className="is-wide"><dt>{t("filePath")}</dt><dd>{media.relativePath}</dd></div> : null}
              {media.checksumSha256 ? <div className="is-wide"><dt>{t("checksum")}</dt><dd>{media.checksumSha256}</dd></div> : null}
            </dl>
          </section>
        );
      })}
    </div>
  );
}
