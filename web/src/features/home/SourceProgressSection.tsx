import { ArrowRight, Database } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { updateSourceDownloadPolicy, type SourceProgress } from "../../app/api";
import { ProgressRing } from "../../components/ProgressRing";
import { useI18n } from "../../i18n/context";
import { formatBytes } from "../status/downloadFormat";
import { DashboardSection, type DashboardTone } from "./DashboardPrimitives";

const numberFormat = new Intl.NumberFormat("zh-CN");
const tones: DashboardTone[] = ["blue", "cyan", "green", "amber", "violet", "rose"];

export function SourceProgressSection({
  sources,
  onOpenSource,
}: {
  sources: SourceProgress[];
  onOpenSource: (sourceId: string) => void;
}) {
  const { t } = useI18n();
  const [localSources, setLocalSources] = useState(sources);
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setLocalSources(sources), [sources]);

  async function toggle(source: SourceProgress) {
    const enabled = !source.autoDownloadEnabled;
    setPending(source.id);
    setError(null);
    setLocalSources((current) => current.map((item) => item.id === source.id ? { ...item, autoDownloadEnabled: enabled } : item));
    try {
      const updated = await updateSourceDownloadPolicy(source.id, enabled);
      setLocalSources((current) => current.map((item) => item.id === source.id ? { ...item, ...updated } : item));
    } catch {
      setLocalSources((current) => current.map((item) => item.id === source.id ? { ...item, autoDownloadEnabled: source.autoDownloadEnabled } : item));
      setError(source.id);
    } finally {
      setPending(null);
    }
  }

  return (
    <DashboardSection title={t("collectionProgressTitle")} className="home-source-section">
      <div className="home-source-list" role="region" aria-label={t("collectionProgressTitle")}>
        {localSources.map((source, index) => {
          const tone = tones[index % tones.length];
          return (
            <article key={source.id} className="home-source-row" data-icon-tone={tone}>
              <button className="home-source-identity" type="button" onClick={() => onOpenSource(source.id)}>
                <span className="app-icon-well" data-icon-tone={tone}><Database size={17} weight="duotone" /></span>
                <span><strong>{source.name}</strong><small>{numberFormat.format(source.archived)} / {numberFormat.format(source.discovered)} {t("archivedWorks")}</small></span>
              </button>
              <ProgressRing value={source.coveragePercent} label={`${source.name} ${t("collectionProgressTitle")}`} compact />
              <dl className="home-source-metrics">
                <div><dt>{t("sourceSize")}</dt><dd>{formatBytes(source.archivedBytes)}</dd></div>
                <div><dt>{t("pendingWork")}</dt><dd>{source.pending + source.running + source.retry}</dd></div>
              </dl>
              <label className="home-policy-toggle">
                <input type="checkbox" role="switch" aria-label={`${t("automaticDownload")} ${source.name}`} checked={source.autoDownloadEnabled} disabled={pending === source.id} onChange={() => void toggle(source)} />
                <span />
              </label>
              <button className="home-source-open" type="button" aria-label={`${t("openSource")} ${source.name}`} onClick={() => onOpenSource(source.id)}><ArrowRight size={17} /></button>
              {error === source.id ? <p className="home-source-error">{t("policyUpdateFailed")}</p> : null}
            </article>
          );
        })}
      </div>
    </DashboardSection>
  );
}
