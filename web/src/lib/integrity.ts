import type { ArchiveIntegrity } from "../app/api";
import { t } from "../i18n/t";
import { formatInteger } from "./format";

/** One line on how much of the backup has been confirmed intact. */
export function integrityHeadline(value: ArchiveIntegrity): string {
  if (value.totalFiles === 0) return t("还没有存下的文件");
  if (value.allCheckedSince) {
    return t("全部 {n} 个文件都完好", { n: formatInteger(value.totalFiles) });
  }
  return t("已检查 {done} / {total} 个文件", {
    done: formatInteger(value.verifiedFiles),
    total: formatInteger(value.totalFiles),
  });
}
