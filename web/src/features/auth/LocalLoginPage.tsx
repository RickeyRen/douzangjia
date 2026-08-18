import { useState, type FormEvent } from "react";

import { loginAdmin } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { AuthFrame } from "../setup/SetupPage";

export function LocalLoginPage({ onComplete }: { onComplete: () => void }) {
  const { t } = useI18n();
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await loginAdmin(password);
      onComplete();
    } catch {
      setError(true);
    }
  }

  return (
    <AuthFrame title={t("localLoginTitle")} body={t("localLoginBody")}>
      <form className="mt-8 grid gap-5" onSubmit={(event) => void submit(event)}>
        <label className="grid gap-2 text-sm font-medium text-[#d7d9de]">
          {t("password")}
          <input className="min-h-12 rounded-lg border border-white/10 bg-white/[.04] px-4 text-base outline-none focus:border-[#f16761]" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error ? <p className="text-sm text-[#f28a85]">{t("invalidCredentials")}</p> : null}
        <button className="min-h-12 rounded-lg bg-[#f16761] px-5 text-sm font-semibold text-[#141518] active:scale-[.98]">{t("login")}</button>
      </form>
    </AuthFrame>
  );
}
