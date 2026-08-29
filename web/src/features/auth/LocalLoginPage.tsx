import { useState, type FormEvent } from "react";

import { loginAdmin } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { AuthFrame } from "../setup/SetupPage";

export function LocalLoginPage({ onComplete }: { onComplete: () => void }) {
  const { t } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await loginAdmin(username, password);
      onComplete();
    } catch {
      setError(true);
    }
  }

  return (
    <AuthFrame title={t("localLoginTitle")} body={t("localLoginBody")}>
      <form className="auth-form" onSubmit={(event) => void submit(event)}>
        <label className="auth-field">
          {t("username")}
          <input type="text" autoComplete="username" value={username} maxLength={32} onChange={(event) => setUsername(event.target.value)} />
        </label>
        <label className="auth-field">
          {t("password")}
          <input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </label>
        {error ? <p className="auth-error">{t("invalidCredentials")}</p> : null}
        <button className="friendly-button friendly-button-primary friendly-button-full" disabled={username.trim().length < 2 || !password}>{t("login")}</button>
      </form>
    </AuthFrame>
  );
}
