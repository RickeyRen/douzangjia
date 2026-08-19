import { useI18n } from "../../i18n/context";

export function AuthorButton({ author, onOpen }: { author: string; onOpen?: (author: string) => void }) {
  const { t } = useI18n();
  return (
    <button
      type="button"
      className="author-archive-link"
      aria-label={`${t("viewCreatorArchivePrefix")}${author}${t("viewCreatorArchiveSuffix")}`}
      onClick={() => onOpen?.(author)}
    >
      @{author}
    </button>
  );
}
