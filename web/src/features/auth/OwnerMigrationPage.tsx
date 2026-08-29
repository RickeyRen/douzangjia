import { useState, type FormEvent } from "react";

import { migrateOwner } from "../../app/api";
import { useI18n } from "../../i18n/context";
import { AuthFrame, PasswordField } from "../setup/SetupPage";

export function OwnerMigrationPage({
  onComplete,
  onUseExistingAccount,
}: {
  onComplete: () => void;
  onUseExistingAccount: () => void;
}) {
  const { t } = useI18n();
  const [username, setUsername] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(false);
    try {
      await migrateOwner(username, currentPassword);
      onComplete();
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame title={t("ownerMigrationTitle")} body={t("ownerMigrationBody")}>
      <form className="auth-form" onSubmit={(event) => void submit(event)}>
        <label className="auth-field">
          {t("newUsername")}
          <input
            type="text"
            autoComplete="username"
            value={username}
            maxLength={32}
            onChange={(event) => setUsername(event.target.value)}
          />
        </label>
        <PasswordField
          label={t("currentPassword")}
          value={currentPassword}
          onChange={setCurrentPassword}
          autoComplete="current-password"
        />
        {error ? <p className="auth-error">{t("invalidCredentials")}</p> : null}
        <button
          className="friendly-button friendly-button-primary friendly-button-full"
          disabled={busy || username.trim().length < 2 || !currentPassword}
        >
          {t("upgradeLocalAccount")}
        </button>
        <button
          className="friendly-button friendly-button-secondary friendly-button-full"
          type="button"
          onClick={onUseExistingAccount}
        >
          {t("useExistingAdmin")}
        </button>
      </form>
    </AuthFrame>
  );
}
