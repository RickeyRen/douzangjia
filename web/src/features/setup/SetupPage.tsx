import { Eye, EyeSlash, LockKey } from "@phosphor-icons/react";
import { useState, type FormEvent } from "react";

import { setupAdmin } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { ThemeToggle } from "../../theme/ThemeToggle";

export function SetupPage({ onComplete }: { onComplete: () => void }) {
  const { t } = useI18n();
  const [username, setUsername] = useState("");
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
      await setupAdmin(username, password);
      onComplete();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("feedError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame title={t("setupTitle")} body={t("setupBody")}>
      <form className="auth-form" onSubmit={(event) => void submit(event)}>
        <label className="auth-field">
          {t("username")}
          <input
            type="text"
            autoComplete="username"
            value={username}
            maxLength={32}
            onChange={(event) => setUsername(event.target.value)}
          />
          <span>{t("usernameHint")}</span>
        </label>
        <PasswordField label={t("password")} value={password} onChange={setPassword} hint={t("passwordHint")} />
        <PasswordField label={t("confirmPassword")} value={confirm} onChange={setConfirm} />
        {error ? <p className="auth-error">{error}</p> : null}
        <button className="friendly-button friendly-button-primary friendly-button-full" disabled={busy || username.trim().length < 2 || password.length < 12}>
          {t("createArchive")}
        </button>
      </form>
    </AuthFrame>
  );
}

export function AuthFrame({ title, body, children }: { title: string; body: string; children: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <main className="auth-shell">
      <ThemeToggle className="auth-theme-toggle" />
      <section className="auth-brand-panel">
        <strong>{t("brand")}</strong>
        <p>{t("brandSubtitle")}</p>
      </section>
      <section className="auth-content">
        <div className="auth-card">
          <div className="auth-icon">
            <LockKey size={22} weight="regular" />
          </div>
          <h1>{title}</h1>
          <p>{body}</p>
          {children}
        </div>
      </section>
    </main>
  );
}

export function PasswordField({
  label,
  value,
  onChange,
  hint,
  autoComplete = "new-password",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  autoComplete?: "new-password" | "current-password";
}) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);
  return (
    <label className="auth-field">
      {label}
      <div className="auth-password">
        <input
          type={visible ? "text" : "password"}
          autoComplete={autoComplete}
          autoCapitalize="off"
          autoCorrect="off"
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
        <button
          type="button"
          className="auth-password-toggle"
          aria-label={visible ? t("hidePassword") : t("showPassword")}
          aria-pressed={visible}
          onClick={(event) => {
            event.preventDefault();
            setVisible((current) => !current);
          }}
        >
          {visible ? <EyeSlash size={18} /> : <Eye size={18} />}
        </button>
      </div>
      {hint ? <span>{hint}</span> : null}
    </label>
  );
}
