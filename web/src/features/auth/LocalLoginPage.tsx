import { useState, type FormEvent } from "react";

import { ApiError, loginAdmin } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { AuthFrame } from "../setup/SetupPage";

export function LocalLoginPage({ onComplete }: { onComplete: () => void }) {
  const { t } = useI18n();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError(null);
    try {
      await loginAdmin(username, password);
      onComplete();
    } catch (failure) {
      setError(describeFailure(failure));
    } finally {
      setPending(false);
    }
  }

  function describeFailure(failure: unknown): string {
    if (failure instanceof ApiError && failure.status === 429) {
      const seconds = Number(failure.details.retryAfterSeconds ?? 0);
      return t("tooManyAttempts").replace("{seconds}", String(seconds || 60));
    }
    if (failure instanceof ApiError && failure.status < 500) return t("invalidCredentials");
    return t("serverUnreachable");
  }

  return (
    <AuthFrame title={t("localLoginTitle")} body={t("localLoginBody")}>
      <form className="auth-form" onSubmit={(event) => void submit(event)}>
        <label className="auth-field">
          {t("username")}
          <input
            type="text"
            autoComplete="username"
            autoFocus
            value={username}
            maxLength={32}
            onChange={(event) => {
              setUsername(event.target.value);
              setError(null);
            }}
          />
        </label>
        <label className="auth-field">
          {t("password")}
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => {
              setPassword(event.target.value);
              setError(null);
            }}
          />
        </label>
        {error ? (
          <p className="auth-error" role="alert">
            {error}
          </p>
        ) : null}
        <button
          className="friendly-button friendly-button-primary friendly-button-full"
          disabled={pending || username.trim().length < 2 || !password}
        >
          {pending ? t("loggingIn") : t("login")}
        </button>
      </form>
    </AuthFrame>
  );
}
