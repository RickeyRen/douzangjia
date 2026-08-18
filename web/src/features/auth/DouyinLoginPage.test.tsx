import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { DouyinLoginPage } from "./DouyinLoginPage";

vi.mock("../../app/api", () => ({
  beginDouyinLogin: vi.fn(),
  getDouyinLogin: vi.fn(),
  submitDouyinPointer: vi.fn(),
  submitDouyinKey: vi.fn(),
  douyinQrUrl: vi.fn((id: string) => `/api/douyin/login/${id}/qr.png`),
  douyinStreamUrl: vi.fn((id: string) => `/api/douyin/login/${id}/stream.mjpeg`),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(cleanup);

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
  expect(screen.getByAltText("抖音登录二维码")).toHaveAttribute(
    "src",
    "/api/douyin/login/login-1/stream.mjpeg",
  );
  expect(screen.getByTestId("douyin-live-view")).toHaveClass("fixed", "inset-0");
  expect(screen.getByAltText("抖音登录二维码")).toHaveClass(
    "max-h-full",
    "max-w-full",
    "object-contain",
  );
  expect(screen.queryByText(/sessionid/i)).not.toBeInTheDocument();
});

it("forwards pointer down, move, and up while the gesture is happening", async () => {
  const awaiting = {
    id: "login-1",
    state: "awaiting_scan" as const,
    expiresAt: "2026-08-18T12:00:00Z",
    hasScreenshot: true,
  };
  vi.mocked(api.beginDouyinLogin).mockResolvedValue(awaiting);
  vi.mocked(api.submitDouyinPointer).mockResolvedValue({ accepted: true });
  const user = userEvent.setup();
  render(<DouyinLoginPage />);
  await user.click(screen.getByRole("button", { name: "登录抖音" }));
  const image = await screen.findByAltText("抖音登录二维码");
  vi.spyOn(image, "getBoundingClientRect").mockReturnValue({
    x: 10,
    y: 20,
    left: 10,
    top: 20,
    right: 530,
    bottom: 700,
    width: 520,
    height: 680,
    toJSON: () => ({}),
  });

  fireEvent.pointerDown(image, { pointerId: 7, clientX: 62, clientY: 292 });
  await vi.waitFor(() => {
    expect(api.submitDouyinPointer).toHaveBeenCalledWith("login-1", {
      action: "down",
      x: 0.1,
      y: 0.4,
    });
  });

  fireEvent.pointerMove(image, { pointerId: 7, clientX: 270, clientY: 292 });
  fireEvent.pointerUp(image, { pointerId: 7, clientX: 478, clientY: 292 });
  await vi.waitFor(() => {
    expect(api.submitDouyinPointer).toHaveBeenNthCalledWith(2, "login-1", {
      action: "move",
      x: 0.5,
      y: 0.4,
    });
    expect(api.submitDouyinPointer).toHaveBeenLastCalledWith("login-1", {
      action: "up",
      x: 0.9,
      y: 0.4,
    });
  });
});

it("forwards OTP digits and editing keys while the live image is focused", async () => {
  const awaiting = {
    id: "login-1",
    state: "awaiting_scan" as const,
    expiresAt: "2026-08-18T12:00:00Z",
    hasScreenshot: true,
  };
  vi.mocked(api.beginDouyinLogin).mockResolvedValue(awaiting);
  vi.mocked(api.submitDouyinKey).mockResolvedValue({ accepted: true });
  const user = userEvent.setup();
  render(<DouyinLoginPage />);
  await user.click(screen.getByRole("button", { name: "登录抖音" }));
  const image = await screen.findByAltText("抖音登录二维码");

  image.focus();
  await user.keyboard("07{Backspace}{Enter}");

  await vi.waitFor(() => {
    expect(api.submitDouyinKey).toHaveBeenNthCalledWith(1, "login-1", "0");
    expect(api.submitDouyinKey).toHaveBeenNthCalledWith(2, "login-1", "7");
    expect(api.submitDouyinKey).toHaveBeenNthCalledWith(3, "login-1", "Backspace");
    expect(api.submitDouyinKey).toHaveBeenNthCalledWith(4, "login-1", "Enter");
  });
});
