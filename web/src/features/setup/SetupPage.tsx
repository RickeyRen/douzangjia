import { LockKey } from "@phosphor-icons/react";
import { useState, type FormEvent } from "react";

import { setupAdmin } from "../../app/api";
import { useI18n } from "../../i18n/context";

export function SetupPage({ onComplete }: { onComplete: () => void }) {
  const { t } = useI18n();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError(t("passwordsMismatch"));
      return;
    }
    setBusy(true);
    setError("");
    try {
      await setupAdmin(password);
      onComplete();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("feedError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame title={t("setupTitle")} body={t("setupBody")}>
      <form className="mt-8 grid gap-5" onSubmit={(event) => void submit(event)}>
        <PasswordField label={t("password")} value={password} onChange={setPassword} hint={t("passwordHint")} />
        <PasswordField label={t("confirmPassword")} value={confirm} onChange={setConfirm} />
        {error ? <p className="text-sm text-[#f28a85]">{error}</p> : null}
        <button className="min-h-12 rounded-lg bg-[#f16761] px-5 text-sm font-semibold text-[#141518] transition-transform active:scale-[.98] disabled:opacity-50" disabled={busy || password.length < 12}>
          {t("createArchive")}
        </button>
      </form>
    </AuthFrame>
  );
}

export function AuthFrame({ title, body, children }: { title: string; body: string; children: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <main className="grid min-h-[100dvh] bg-[#0c0e11] text-[#f7f8fa] md:grid-cols-[minmax(280px,0.8fr)_minmax(420px,1.2fr)]">
      <section className="hidden border-r border-white/10 p-12 md:flex md:flex-col md:justify-between">
        <strong className="text-2xl tracking-[-0.04em]">{t("brand")}</strong>
        <p className="max-w-[24ch] text-sm leading-6 text-[#747a84]">{t("brandSubtitle")}</p>
      </section>
      <section className="flex items-center px-6 py-12 md:px-[10vw]">
        <div className="w-full max-w-[430px] border-t border-white/10 pt-8">
          <div className="mb-8 flex h-11 w-11 items-center justify-center rounded-xl border border-white/10 bg-white/[.04]">
            <LockKey size={22} weight="regular" />
          </div>
          <h1 className="text-3xl font-semibold tracking-[-0.035em]">{title}</h1>
          <p className="mt-3 text-[15px] leading-7 text-[#969ba5]">{body}</p>
          {children}
        </div>
      </section>
    </main>
  );
}

function PasswordField({ label, value, onChange, hint }: { label: string; value: string; onChange: (value: string) => void; hint?: string }) {
  return (
    <label className="grid gap-2 text-sm font-medium text-[#d7d9de]">
      {label}
      <input
        className="min-h-12 rounded-lg border border-white/10 bg-white/[.04] px-4 text-base outline-none transition-colors focus:border-[#f16761]"
        type="password"
        autoComplete="new-password"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      {hint ? <span className="text-xs font-normal text-[#747a84]">{hint}</span> : null}
    </label>
  );
}
