import { act, cleanup, fireEvent, render as renderView, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import * as api from "../../app/api";
import { ThemeProvider } from "../../theme/ThemeProvider";
import { DouyinLoginPage } from "./DouyinLoginPage";

function render(ui: ReactElement) {
  return renderView(<ThemeProvider>{ui}</ThemeProvider>);
}

vi.mock("../../app/api", () => ({
  beginDouyinLogin: vi.fn(),
  getDouyinLogin: vi.fn(),
  submitDouyinPointer: vi.fn(),
  submitDouyinKey: vi.fn(),
  douyinQrUrl: vi.fn((id: string) => `/api/douyin/login/${id}/qr.png`),
  douyinStreamUrl: vi.fn((id: string) => `/api/douyin/login/${id}/stream.mjpeg`),
}));

class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  binaryType = "";
  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(payload: string) {
    this.sent.push(payload);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
  }
}

function openBrowserSocket() {
  const socket = FakeWebSocket.instances.at(-1)!;
  act(() => {
    socket.readyState = FakeWebSocket.OPEN;
    socket.onopen?.();
    socket.onmessage?.({
      data: JSON.stringify({
        type: "status",
        state: "awaiting_scan",
        width: 1280,
        height: 800,
        transport: "cdp",
      }),
    } as MessageEvent);
  });
  return socket;
}

beforeEach(() => {
  vi.clearAllMocks();
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the full persistent NAS browser without exposing cookie text", async () => {
  vi.mocked(api.beginDouyinLogin).mockResolvedValue({
    id: "login-1",
    state: "awaiting_scan",
    expiresAt: "2026-08-18T12:00:00Z",
    hasScreenshot: true,
  });
  render(<DouyinLoginPage />);
  expect(screen.getByRole("main")).toHaveClass("auth-shell");
  expect(screen.getByRole("button", { name: "切换到亮色主题" })).toBeVisible();
  expect(api.beginDouyinLogin).toHaveBeenCalledOnce();

  const canvas = await screen.findByLabelText("抖音登录二维码");
  openBrowserSocket();
  expect(canvas).toBeVisible();
  expect(canvas.tagName).toBe("CANVAS");
  expect(canvas).toHaveAttribute("width", "1280");
  expect(canvas).toHaveAttribute("height", "800");
  expect(screen.getByTestId("douyin-live-view")).toHaveClass("remote-browser-shell");
  expect(canvas).toHaveClass("remote-browser-frame");
  expect(canvas.parentElement).toHaveClass("remote-browser-stage");
  expect(canvas.parentElement).not.toHaveClass("grid");
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
  render(<DouyinLoginPage />);
  const canvas = await screen.findByLabelText("抖音登录二维码");
  const socket = openBrowserSocket();
  vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({
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

  fireEvent.pointerDown(canvas, { pointerId: 7, clientX: 62, clientY: 292 });
  fireEvent.pointerMove(canvas, { pointerId: 7, clientX: 270, clientY: 292 });
  fireEvent.pointerUp(canvas, { pointerId: 7, clientX: 478, clientY: 292 });
  await vi.waitFor(() => {
    expect(socket.sent.map((payload) => JSON.parse(payload))).toEqual([
      { type: "pointer", action: "down", x: 0.1, y: 0.4 },
      { type: "pointer", action: "move", x: 0.5, y: 0.4 },
      { type: "pointer", action: "up", x: 0.9, y: 0.4 },
    ]);
  });
  expect(api.submitDouyinPointer).not.toHaveBeenCalled();
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
  const canvas = await screen.findByLabelText("抖音登录二维码");
  const socket = openBrowserSocket();

  canvas.focus();
  await user.keyboard("07{Backspace}{Enter}");

  await vi.waitFor(() => {
    expect(socket.sent.map((payload) => JSON.parse(payload))).toEqual([
      { type: "key", key: "0" },
      { type: "key", key: "7" },
      { type: "key", key: "Backspace" },
      { type: "key", key: "Enter" },
    ]);
  });
  expect(api.submitDouyinKey).not.toHaveBeenCalled();
});

it("tells people the page is opening while the NAS browser is busy", async () => {
  let release: (value: api.LoginStatus) => void = () => undefined;
  vi.mocked(api.beginDouyinLogin).mockReturnValue(
    new Promise<api.LoginStatus>((resolve) => {
      release = resolve;
    }),
  );
  render(<DouyinLoginPage />);

  expect(screen.getByRole("status")).toHaveTextContent("正在打开抖音登录页");
  expect(screen.queryByRole("button", { name: "登录抖音" })).not.toBeInTheDocument();

  await act(async () => {
    release({ id: "login-1", state: "expired", expiresAt: "2026-08-18T12:00:00Z", hasScreenshot: false });
  });
  expect(screen.getByRole("status")).toHaveTextContent("二维码已过期");
  expect(screen.getByRole("button", { name: "登录抖音" })).toBeVisible();
});
