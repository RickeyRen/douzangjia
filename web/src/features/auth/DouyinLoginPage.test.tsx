import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { DouyinLoginPage } from "./DouyinLoginPage";

vi.mock("../../app/api", () => ({
  beginDouyinLogin: vi.fn(),
  getDouyinLogin: vi.fn(),
  douyinQrUrl: vi.fn((id: string) => `/api/douyin/login/${id}/qr.png`),
}));

it("shows the NAS-generated QR without exposing cookie text", async () => {
  vi.mocked(api.beginDouyinLogin).mockResolvedValue({
    id: "login-1",
    state: "awaiting_scan",
    expiresAt: "2026-08-18T12:00:00Z",
    hasScreenshot: true,
  });
  const user = userEvent.setup();
  render(<DouyinLoginPage />);
  await user.click(screen.getByRole("button", { name: "登录抖音" }));

  expect(await screen.findByAltText("抖音登录二维码")).toBeVisible();
  expect(screen.queryByText(/sessionid/i)).not.toBeInTheDocument();
});
