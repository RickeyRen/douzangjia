import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { ThemeProvider } from "../theme/ThemeProvider";
import { makeHealth, makeItem } from "../test/fixtures";
import * as api from "./api";
import { App } from "./App";

vi.mock("./api", async (original) => ({
  ...(await original<typeof api>()),
  fetchStatus: vi.fn(),
  fetchHome: vi.fn(),
  fetchLibrarySources: vi.fn(),
  fetchSyncHealth: vi.fn(),
  logout: vi.fn(),
}));

const status: api.BootstrapStatus = {
  configured: true,
  ownerSetupRequired: false,
  authenticated: true,
  douyinAuthenticated: true,
  douyinHealth: {
    sessionStored: true,
    status: "healthy",
    lastVerifiedAt: null,
    lastSyncAt: null,
    lastFailureAt: null,
    errorCode: null,
    consecutiveFailures: 0,
    account: { id: "1", nickname: "天鹰座", uniqueId: "SUPRIM", avatarUrl: null },
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  window.location.hash = "#/";
  vi.mocked(api.fetchStatus).mockResolvedValue(status);
  vi.mocked(api.fetchLibrarySources).mockResolvedValue({ items: [] });
  vi.mocked(api.fetchSyncHealth).mockResolvedValue(makeHealth());
  vi.mocked(api.fetchHome).mockResolvedValue({
    stats: { items: 3, videos: 2, galleries: 1, downloadedItems: 1, archivedBytes: 1024, creators: 1, starred: 0, gone: 0, remoteChecked: 0 },
    health: makeHealth(),
    recent: [makeItem()],
    starred: [],
    gone: [],
    shelves: [],
    creators: [],
  });
});
afterEach(cleanup);

function renderApp() {
  return render(
    <ThemeProvider>
      <App />
    </ThemeProvider>,
  );
}

it("lands signed-in owners on a content-first home page", async () => {
  renderApp();

  expect(await screen.findByRole("heading", { name: /天鹰座/ })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "最近收藏" })).toBeInTheDocument();
  expect(screen.getByRole("navigation", { name: "主导航" })).toBeInTheDocument();
});

it("re-scans from settings and can return without logging in", async () => {
  const user = userEvent.setup();
  window.location.hash = "#/settings";
  renderApp();

  await user.click(await screen.findByRole("button", { name: "重新扫码" }));
  expect(await screen.findByRole("heading", { name: "扫码连接你的收藏" })).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "返回资料库" }));
  expect(await screen.findByRole("heading", { name: "设置" })).toBeInTheDocument();
});
