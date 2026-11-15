import { ShieldCheck, ShieldWarning } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { fetchArchiveIntegrity, type ArchiveIntegrity } from "../app/api";
import { formatInteger, formatRelative } from "../lib/format";
import { integrityHeadline } from "../lib/integrity";
import { Progress } from "../ui/primitives";
import { t } from "../i18n/t";

export function IntegrityPanel({ initial = null }: { initial?: ArchiveIntegrity | null }) {
  const [value, setValue] = useState<ArchiveIntegrity | null>(initial);
  useEffect(() => {
    if (initial) return;
    let active = true;
    const load = () =>
      fetchArchiveIntegrity()
        .then((next) => active && setValue(next))
        .catch(() => undefined);
    void load();
    const timer = window.setInterval(load, 60_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [initial]);

  const Glyph = value && value.repairingFiles > 0 ? ShieldWarning : ShieldCheck;
  // The bar follows the slow part (hashing) once every file has been seen.
  const done = value ? (value.allPresentSince ? value.verifiedFiles : (value.presentFiles ?? value.verifiedFiles)) : 0;
  const percent = value && value.totalFiles ? (done / value.totalFiles) * 100 : 0;
  return (
    <section className="panel integrity">
      <div className="panel-head">
        <div>
          <h2>{t("备份自检")}</h2>
          <p>{t("后台慢慢核对每个已存文件还在、没有损坏；出问题会自动重新下载。")}</p>
        </div>
        <Glyph size={20} className="panel-icon" />
      </div>
      {value ? (
        <>
          <div className="meter-label">
            <strong className="num">{integrityHeadline(value)}</strong>
            <span>
              {value.allCheckedSince
                ? t("最早一次核对在 {when}", { when: formatRelative(value.allCheckedSince) })
                : value.allPresentSince
                  ? t("全部文件最近一次清点在 {when}", { when: formatRelative(value.allPresentSince) })
                  : value.lastCheckedAt
                  ? t("最近核对 {when}", { when: formatRelative(value.lastCheckedAt) })
                  : t("马上开始")}
            </span>
          </div>
          <Progress value={percent} tone={value.repairingFiles > 0 ? "warning" : "info"} />
          {value.repairingFiles > 0 ? (
            <p className="integrity-note is-warning">
              {t("发现 {n} 个文件丢失或损坏，已经在重新下载；损坏的旧文件移到了 quarantine 文件夹，没有删除。", {
                n: formatInteger(value.repairingFiles),
              })}
            </p>
          ) : null}
          {value.repairedFiles > 0 ? (
            <p className="integrity-note">{t("已自动补回 {n} 个文件。", { n: formatInteger(value.repairedFiles) })}</p>
          ) : null}
        </>
      ) : (
        <p className="integrity-note">{t("正在读取…")}</p>
      )}
    </section>
  );
}
