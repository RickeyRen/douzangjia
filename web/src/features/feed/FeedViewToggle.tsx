import { Rectangle, SquaresFour } from "@phosphor-icons/react";

import { useI18n } from "../../i18n/context";

export type FeedViewMode = "focus" | "grid";

export function FeedViewToggle({ mode, onChange }: { mode: FeedViewMode; onChange: (mode: FeedViewMode) => void }) {
  const { t } = useI18n();
  return (
    <div role="group" aria-label={t("feedViewMode")} className="feed-view-toggle">
      <button type="button" aria-label={t("singlePostView")} aria-pressed={mode === "focus"} onClick={() => onChange("focus")}>
        <Rectangle size={18} weight={mode === "focus" ? "fill" : "regular"} />
      </button>
      <button type="button" aria-label={t("multiPostView")} aria-pressed={mode === "grid"} onClick={() => onChange("grid")}>
        <SquaresFour size={18} weight={mode === "grid" ? "fill" : "regular"} />
      </button>
    </div>
  );
}
