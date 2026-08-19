import { ArrowClockwise, CheckCircle, Clock, SpinnerGap, WarningCircle } from "@phosphor-icons/react";

import type { LocalArchiveState } from "../../app/api";
import { useI18n } from "../../i18n/context";

const stateMeta = {
  downloaded: { key: "localDownloaded", icon: CheckCircle },
  downloading: { key: "localDownloading", icon: SpinnerGap },
  waiting: { key: "localWaiting", icon: Clock },
  retry: { key: "localRetry", icon: ArrowClockwise },
  failed: { key: "localFailed", icon: WarningCircle },
} as const;

export function LocalStateBadge({ local, detailed = false }: { local: LocalArchiveState; detailed?: boolean }) {
  const { t } = useI18n();
  const meta = stateMeta[local.state];
  const Icon = meta.icon;
  const assets = local.totalAssets > 0 ? `${local.readyAssets}/${local.totalAssets}` : null;
  return (
    <span className={`local-state-badge local-state-${local.state}`}>
      <Icon size={15} weight={local.state === "downloaded" ? "fill" : "bold"} className={local.state === "downloading" ? "is-spinning" : undefined} />
      <span>{t(meta.key)}</span>
      {detailed && assets ? <small>{assets}</small> : null}
    </span>
  );
}
