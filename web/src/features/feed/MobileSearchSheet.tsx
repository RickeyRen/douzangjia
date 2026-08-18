import { MagnifyingGlass, X, XCircle } from "@phosphor-icons/react";

import { useI18n } from "../../i18n/context";

export function MobileSearchSheet({ value, onChange, onClose }: { value: string; onChange: (value: string) => void; onClose: () => void }) {
  const { t } = useI18n();
  return (
    <div className="fixed inset-0 z-[8] bg-[#0c0e11]/96 backdrop-blur-xl lg:hidden" onClick={onClose}>
      <section role="dialog" aria-modal="true" aria-label={t("searchArchive")} className="min-h-[100dvh] px-4 pb-[calc(88px+env(safe-area-inset-bottom))] pt-[calc(14px+env(safe-area-inset-top))]" onClick={(event) => event.stopPropagation()}>
        <header className="flex min-h-12 items-center gap-3">
          <label className="flex min-h-12 min-w-0 flex-1 items-center gap-3 rounded-2xl border border-white/10 bg-white/[.06] px-4 shadow-[inset_0_1px_0_rgba(255,255,255,.06)] focus-within:border-white/20">
            <MagnifyingGlass size={20} className="shrink-0 text-[#9096a0]" />
            <input autoFocus type="search" aria-label={t("searchArchive")} className="min-w-0 flex-1 bg-transparent text-base text-white outline-none placeholder:text-[#737984]" value={value} onChange={(event) => onChange(event.target.value)} placeholder={t("searchArchive")} />
            {value ? <button type="button" onClick={() => onChange("")} aria-label={t("clearSearch")} className="touch-target grid h-11 w-11 shrink-0 place-items-center rounded-full text-[#aeb3bc] active:scale-[.96]"><XCircle size={21} /></button> : null}
          </label>
          <button type="button" onClick={onClose} aria-label={t("closeSearch")} className="touch-target grid h-12 w-12 shrink-0 place-items-center rounded-full border border-white/10 bg-white/[.04] active:scale-[.96]"><X size={21} /></button>
        </header>
        <p className="mt-5 px-1 text-sm leading-6 text-[#858b95]">{t("searchHint")}</p>
      </section>
    </div>
  );
}
