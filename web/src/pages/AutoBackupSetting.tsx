import { ArrowClockwise } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { backupNow, fetchBackupStatus, type BackupStatus } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { formatBytes, formatRelative } from "../lib/format";
import { Spinner } from "../ui/primitives";
import { t } from "../i18n/t";

/** Daily self-checked copies of the database kept on the NAS. */
export function AutoBackupSetting({ initial = null }: { initial?: BackupStatus | null }) {
  const { toast } = useAppData();
  const [status, setStatus] = useState<BackupStatus | null>(initial);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (initial) return;
    fetchBackupStatus()
      .then(setStatus)
      .catch(() => undefined);
  }, [initial]);

  async function runNow() {
    setBusy(true);
    try {
      setStatus(await backupNow());
      toast(t("已备份数据库"));
    } catch {
      toast(t("备份没有完成，请稍后重试"));
    } finally {
      setBusy(false);
    }
  }

  const latest = status?.backups[0];
  return (
    <div className="setting">
      <div className="setting-text">
        <strong>{t("每天自动备份数据库")}</strong>
        <small>
          {status === null
            ? t("正在读取…")
            : latest
              ? t("最近一次 {when}（{size}），保留最近 {keep} 份，在归档目录的 {dir}/ 下；每份备份都会先检查能正常打开。", {
                  when: formatRelative(latest.createdAt),
                  size: formatBytes(latest.bytes),
                  keep: status.keep,
                  dir: status.directory,
                })
              : t("还没有自动备份，一小时内会做第一份。")}
          {status?.lastError ? ` ${t("上次备份失败：{reason}", { reason: status.lastError })}` : ""}
        </small>
      </div>
      <button className="btn btn-secondary btn-sm" type="button" onClick={() => void runNow()} disabled={busy}>
        {busy ? <Spinner /> : <ArrowClockwise size={15} weight="bold" />}
        {t("立即备份")}
      </button>
    </div>
  );
}
