import { MagnifyingGlass, X, XCircle } from "@phosphor-icons/react";

import { useI18n } from "../../i18n/context";

export function MobileSearchSheet({ value, onChange, onClose }: { value: string; onChange: (value: string) => void; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <div className="mobile-search-overlay" onClick={onClose}>
      <section role="dialog" aria-modal="true" aria-label={t("searchArchive")} className="mobile-search-sheet" onClick={(event) => event.stopPropagation()}>
        <header className="mobile-search-header">
          <label className="mobile-search-field">
            <MagnifyingGlass size={20} />
            <input autoFocus type="search" aria-label={t("searchArchive")} value={value} onChange={(event) => onChange(event.target.value)} placeholder={t("searchArchive")} />
            {value ? <button type="button" onClick={() => onChange("")} aria-label={t("clearSearch")} className="touch-target"><XCircle size={21} /></button> : null}
          </label>
          <button type="button" onClick={onClose} aria-label={t("closeSearch")} className="touch-target utility-close-button"><X size={21} /></button>
        </header>
        <p className="mobile-search-hint">{t("searchHint")}</p>
      </section>
    </div>
  );
}
