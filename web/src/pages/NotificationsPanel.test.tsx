import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { WithAppData } from "../test/appData";
import { makeAppData } from "../test/makeAppData";
import { NotificationsPanel } from "./NotificationsPanel";

vi.mock("../app/api", async (original) => ({
  ...(await original<typeof api>()),
  fetchSettings: vi.fn(),
  updateSettings: vi.fn(),
  testNotifications: vi.fn(),
}));

function payload(notifications: Record<string, unknown>): api.SettingsPayload {
  const values: api.RuntimeSettings = { sync_interval_seconds: 300, download_workers: 2, remote_check_per_day: 200, notifications };
  return { values, defaults: values, overridden: [] };
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchSettings).mockResolvedValue(payload({}));
});
afterEach(cleanup);

it("saves channel settings and sends a test message", async () => {
  vi.mocked(api.updateSettings).mockImplementation(async (changes) => payload(changes.notifications as Record<string, unknown>));
  vi.mocked(api.testNotifications).mockResolvedValue({ results: { bark: "ok" } });
  const user = userEvent.setup();
  const appData = makeAppData();
  render(
    <WithAppData value={appData}>
      <NotificationsPanel />
    </WithAppData>,
  );

  expect(screen.getByRole("button", { name: "发送测试" })).toBeDisabled();
  await user.type(screen.getByLabelText("Bark 推送地址"), "https://api.day.app/abc");
  await user.click(screen.getByRole("switch", { name: "问题恢复后通知一次" }));
  await user.click(screen.getByRole("button", { name: "发送测试" }));

  await waitFor(() => expect(api.testNotifications).toHaveBeenCalled());
  expect(api.updateSettings).toHaveBeenCalledWith({
    notifications: expect.objectContaining({ bark: { url: "https://api.day.app/abc" }, events: { recovered: false } }),
  });
  expect(await screen.findByText("bark 已送达")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存" })).toBeDisabled();
});
