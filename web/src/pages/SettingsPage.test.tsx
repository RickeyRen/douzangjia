import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { WithAppData } from "../test/appData";
import { ThemeProvider } from "../theme/ThemeProvider";
import { makeAppData } from "../test/makeAppData";
import { SyncSettingsPanel } from "./SettingsPage";

vi.mock("../app/api", async (original) => ({
  ...(await original<typeof api>()),
  fetchSettings: vi.fn(),
  updateSettings: vi.fn(),
}));

const payload = (values: Partial<api.RuntimeSettings> = {}): api.SettingsPayload => {
  const base: api.RuntimeSettings = { sync_interval_seconds: 300, download_workers: 2, remote_check_per_day: 200, notifications: {}, ...values };
  return { values: base, defaults: base, overridden: [] };
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchSettings).mockResolvedValue(payload());
});
afterEach(cleanup);

it("saves a new sync interval and reports it took effect", async () => {
  vi.mocked(api.updateSettings).mockResolvedValue(payload({ sync_interval_seconds: 900 }));
  const appData = makeAppData();
  const user = userEvent.setup();
  render(
    <WithAppData value={appData}>
      <SyncSettingsPanel />
    </WithAppData>,
  );
  await waitFor(() => expect(screen.getByLabelText("同步间隔")).toHaveValue("300"));

  await user.selectOptions(screen.getByLabelText("同步间隔"), "900");

  expect(api.updateSettings).toHaveBeenCalledWith({ sync_interval_seconds: 900 });
  await waitFor(() => expect(appData.toast).toHaveBeenCalledWith("设置已生效"));
  expect(appData.refreshHealth).toHaveBeenCalled();
});

it("rolls the control back when saving fails", async () => {
  vi.mocked(api.updateSettings).mockRejectedValue(new Error("nope"));
  const appData = makeAppData();
  const user = userEvent.setup();
  render(
    <WithAppData value={appData}>
      <SyncSettingsPanel />
    </WithAppData>,
  );
  await waitFor(() => expect(screen.getByLabelText("下载并发数")).toHaveValue("2"));

  await user.selectOptions(screen.getByLabelText("下载并发数"), "4");

  await waitFor(() => expect(appData.toast).toHaveBeenCalledWith("保存失败，请稍后重试"));
  expect(screen.getByLabelText("下载并发数")).toHaveValue("2");
});

it("shows the running version and a database backup link", async () => {
  const { SettingsPage } = await import("./SettingsPage");
  render(
    <ThemeProvider>
      <WithAppData value={makeAppData({ about: { version: "0.2.0", commit: "deadbeefcafe" } })}>
        <SettingsPage />
      </WithAppData>
    </ThemeProvider>,
  );

  expect(screen.getByText("版本 0.2.0 · 构建 deadbee · MIT 开源")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "下载" })).toHaveAttribute("href", "/api/backup/database");
});
