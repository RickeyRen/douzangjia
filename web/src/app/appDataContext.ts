import { createContext, useContext } from "react";

import type { Album, DouyinHealth, FeedItem, LibrarySource, SyncHealth } from "./api";

export type AppData = {
  sources: LibrarySource[];
  refreshSources: () => Promise<void>;
  albums: Album[];
  refreshAlbums: () => Promise<void>;
  health: SyncHealth | null;
  refreshHealth: () => Promise<void>;
  account: DouyinHealth | null;
  about: { version: string; commit: string };
  toast: (message: string) => void;
  toggleStar: (item: FeedItem) => Promise<boolean | null>;
  requestDouyinLogin: () => void;
  logoutDouyin: () => Promise<void>;
  logout: () => void;
};

export const AppDataContext = createContext<AppData | null>(null);

export function useAppData(): AppData {
  const context = useContext(AppDataContext);
  if (!context) throw new Error("useAppData must be used inside AppDataProvider");
  return context;
}
