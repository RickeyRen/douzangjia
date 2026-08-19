import { useI18n } from "../../i18n/context";

export function AuthorButton({ creatorId, author, onOpen }: { creatorId?: string | null; author: string; onOpen?: (creatorId: string | null, author: string) => void }) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      className="author-archive-link"
      aria-label={`${t("viewCreatorArchivePrefix")}${author}${t("viewCreatorArchiveSuffix")}`}
      onClick={() => onOpen?.(creatorId ?? null, author)}
    >
      @{author}
    </button>
  );
}
