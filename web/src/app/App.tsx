import { useCallback, useEffect, useState } from "react";

import { DouyinLoginPage } from "../features/auth/DouyinLoginPage";
import { LocalLoginPage } from "../features/auth/LocalLoginPage";
import { OwnerMigrationPage } from "../features/auth/OwnerMigrationPage";
import { SetupPage } from "../features/setup/SetupPage";
import { ActivityPage } from "../pages/ActivityPage";
import { CreatorPage, CreatorsPage } from "../pages/CreatorsPage";
import { HomePage } from "../pages/HomePage";
import { LibraryPage } from "../pages/LibraryPage";
import { SettingsPage } from "../pages/SettingsPage";
import { Shell } from "../shell/Shell";
import { ErrorState, Spinner } from "../ui/primitives";
import { fetchStatus, logout as logoutRequest, type BootstrapStatus } from "./api";
import { AppDataProvider } from "./AppData";
import { useRoute } from "./router";

export function App() {
  const [status, setStatus] = useState<BootstrapStatus | null>(null);
  const [error, setError] = useState(false);
  const [useExistingAccount, setUseExistingAccount] = useState(false);
  const [relogin, setRelogin] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setStatus(await fetchStatus());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const logout = useCallback(async () => {
    try {
      await logoutRequest();
    } finally {
      await refresh();
    }
  }, [refresh]);

  if (error) {
    return (
      <div className="app-loading">
        <ErrorState message="连不上抖藏家服务，请确认 NAS 上的容器正在运行。" onRetry={() => void refresh()} />
      </div>
    );
  }
  if (!status) {
    return (
      <div className="app-loading">
        <Spinner size={26} />
      </div>
    );
  }
  if (!status.configured) return <SetupPage onComplete={() => void refresh()} />;
  if (status.ownerSetupRequired && !status.authenticated && !useExistingAccount) {
    return <OwnerMigrationPage onComplete={() => void refresh()} onUseExistingAccount={() => setUseExistingAccount(true)} />;
  }
  if (!status.authenticated) return <LocalLoginPage onComplete={() => void refresh()} />;
  if (!status.douyinAuthenticated || relogin) {
    return (
      <DouyinLoginPage
        onAuthenticated={() => {
          setRelogin(false);
          void refresh();
        }}
        onCancel={status.douyinAuthenticated ? () => setRelogin(false) : undefined}
      />
    );
  }
  return (
    <AppDataProvider account={status.douyinHealth ?? null} onRequestDouyinLogin={() => setRelogin(true)} onLogout={() => void logout()}>
      <Shell>
        <RoutedPage />
      </Shell>
    </AppDataProvider>
  );
}

function RoutedPage() {
  const route = useRoute();
  switch (route.name) {
    case "home":
      return <HomePage />;
    case "library":
    case "starred":
    case "search":
    case "album":
    case "tag":
    case "gone":
      return <LibraryPage route={route} />;
    case "creators":
      return <CreatorsPage query={route.query} />;
    case "creator":
      return <CreatorPage route={route} />;
    case "activity":
      return <ActivityPage />;
    case "settings":
      return <SettingsPage />;
  }
}
