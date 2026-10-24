import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  fetchLibrarySources,
  fetchSyncHealth,
  setItemStar,
  type DouyinHealth,
  type FeedItem,
  type LibrarySource,
  type SyncHealth,
} from "./api";
import { AppDataContext } from "./appDataContext";

const HEALTH_REFRESH_MS = 30_000;

export function AppDataProvider({
  account,
  onRequestDouyinLogin,
  onLogout,
  children,
}: {
  account: DouyinHealth | null;
  onRequestDouyinLogin: () => void;
  onLogout: () => void;
  children: ReactNode;
}) {
  const [sources, setSources] = useState<LibrarySource[]>([]);
  const [health, setHealth] = useState<SyncHealth | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);

  const refreshSources = useCallback(async () => {
    try {
      setSources((await fetchLibrarySources()).items);
    } catch {
      // The sidebar keeps the last known list; pages show their own errors.
    }
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await fetchSyncHealth());
    } catch {
      // A transient failure should not flash a false alarm.
    }
  }, []);

  useEffect(() => {
    void refreshSources();
    void refreshHealth();
    const timer = window.setInterval(() => void refreshHealth(), HEALTH_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refreshHealth, refreshSources]);

  const toast = useCallback((text: string) => {
    window.clearTimeout(toastTimer.current);
    setMessage(text);
    toastTimer.current = window.setTimeout(() => setMessage(null), 2400);
  }, []);

  const toggleStar = useCallback(
    async (item: FeedItem) => {
      const next = !item.starred;
      try {
        await setItemStar(item.awemeId, next);
        toast(next ? "已加入精选" : "已从精选移除");
        return next;
      } catch {
        toast("操作失败，请稍后重试");
        return null;
      }
    },
    [toast],
  );

  const value = useMemo(
    () => ({
      sources,
      refreshSources,
      health,
      refreshHealth,
      account,
      toast,
      toggleStar,
      requestDouyinLogin: onRequestDouyinLogin,
      logout: onLogout,
    }),
    [account, health, onLogout, onRequestDouyinLogin, refreshHealth, refreshSources, sources, toast, toggleStar],
  );

  return (
    <AppDataContext.Provider value={value}>
      {children}
      {message ? (
        <div className="toast" role="status">
          {message}
        </div>
      ) : null}
    </AppDataContext.Provider>
  );
}
