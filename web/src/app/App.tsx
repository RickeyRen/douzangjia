import { useEffect, useState } from "react";

import { fetchStatus, type BootstrapStatus } from "./api";
import { DouyinLoginPage } from "../features/auth/DouyinLoginPage";
import { LocalLoginPage } from "../features/auth/LocalLoginPage";
import { FeedPage } from "../features/feed/FeedPage";
import { SetupPage } from "../features/setup/SetupPage";
import { useI18n } from "../i18n/context";

export function App() {
  const { t } = useI18n();
  const [status, setStatus] = useState<BootstrapStatus | null>(null);
  const [error, setError] = useState(false);

  async function refresh() {
    try {
      setStatus(await fetchStatus());
      setError(false);
    } catch {
      setError(true);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  if (error) return <div className="grid min-h-[100dvh] place-items-center bg-[#0c0e11] px-6 text-center text-[#f7f8fa]"><div><p>{t("feedError")}</p><button className="mt-5 rounded-lg border border-white/10 px-5 py-3 text-sm" onClick={() => void refresh()}>{t("retry")}</button></div></div>;
  if (!status) return <div className="grid min-h-[100dvh] place-items-center bg-[#0c0e11] text-sm text-[#747a84]">{t("loadingArchive")}</div>;
  if (!status.configured) return <SetupPage onComplete={() => void refresh()} />;
  if (!status.authenticated) return <LocalLoginPage onComplete={() => void refresh()} />;
  if (!status.douyinAuthenticated) return <DouyinLoginPage onAuthenticated={() => void refresh()} />;
  return <FeedPage />;
}
