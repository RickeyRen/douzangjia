import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import { WithAppData } from "../test/appData";
import { makeAppData } from "../test/makeAppData";
import { makeHealth } from "../test/fixtures";
import { HealthBanner } from "./Shell";

vi.mock("../app/api", async (original) => ({ ...(await original<typeof api>()), triggerSync: vi.fn(async () => ({ runId: 9 })) }));

beforeEach(() => {
  vi.clearAllMocks();
  window.location.hash = "#/";
});
afterEach(cleanup);

it("stays hidden while sync is healthy", () => {
  const { container } = render(
    <WithAppData value={makeAppData({ health: makeHealth() })}>
      <HealthBanner />
    </WithAppData>,
  );
  expect(container).toBeEmptyDOMElement();
});

it("lets people restart a stalled sync from any page", async () => {
  const user = userEvent.setup();
  const appData = makeAppData({ health: makeHealth({ state: "stale", lastSuccessAt: Math.round(Date.now() / 1000) - 29 * 86_400 }) });
  render(
    <WithAppData value={appData}>
      <HealthBanner />
    </WithAppData>,
  );

  expect(screen.getByRole("alert")).toHaveTextContent("同步已经停止");
  await user.click(screen.getByRole("button", { name: "立即同步" }));

  expect(api.triggerSync).toHaveBeenCalledWith(false);
  expect(appData.toast).toHaveBeenCalledWith("已开始同步");
});

it("sends people to the QR login when Douyin logged them out", async () => {
  const user = userEvent.setup();
  const appData = makeAppData({ health: makeHealth({ state: "login_required" }) });
  render(
    <WithAppData value={appData}>
      <HealthBanner />
    </WithAppData>,
  );

  await user.click(screen.getByRole("button", { name: "重新扫码" }));

  expect(appData.requestDouyinLogin).toHaveBeenCalledOnce();
});
