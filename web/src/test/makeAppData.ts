import { vi } from "vitest";

import type { AppData } from "../app/appDataContext";

export function makeAppData(overrides: Partial<AppData> = {}): AppData {
  return {
    sources: [],
    refreshSources: vi.fn(async () => undefined),
    health: null,
    refreshHealth: vi.fn(async () => undefined),
    account: null,
    toast: vi.fn(),
    toggleStar: vi.fn(async (item) => !item.starred),
    requestDouyinLogin: vi.fn(),
    logout: vi.fn(),
    ...overrides,
  };
}
