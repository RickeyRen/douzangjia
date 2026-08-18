import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { useDouyinBrowserSocket } from "./useDouyinBrowserSocket";

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

  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  emit(data: Blob | string) {
    this.onmessage?.({ data } as MessageEvent);
  }

  send(payload: string) {
    this.sent.push(payload);
  }

  close() {
    this.readyState = FakeWebSocket.CLOSED;
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it("draws only the latest frame when decoding falls behind", async () => {
  const canvas = document.createElement("canvas");
  const canvasRef = { current: canvas };
  const drawImage = vi.fn();
  vi.spyOn(canvas, "getContext").mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
  const firstDecode = deferred<ImageBitmap>();
  const firstBitmap = { close: vi.fn() } as unknown as ImageBitmap;
  const latestBitmap = { close: vi.fn() } as unknown as ImageBitmap;
  const createImageBitmap = vi
    .fn<typeof globalThis.createImageBitmap>()
    .mockReturnValueOnce(firstDecode.promise)
    .mockResolvedValueOnce(latestBitmap);
  vi.stubGlobal("createImageBitmap", createImageBitmap);

  renderHook(() =>
    useDouyinBrowserSocket({
      loginId: "login-1",
      canvasRef,
    }),
  );
  const socket = FakeWebSocket.instances[0];
  act(() => socket.open());
  act(() =>
    socket.emit(
      JSON.stringify({
        type: "status",
        state: "awaiting_scan",
        width: 1280,
        height: 800,
        transport: "cdp",
      }),
    ),
  );
  const first = new Blob(["first"], { type: "image/jpeg" });
  const latest = new Blob(["latest"], { type: "image/jpeg" });

  act(() => socket.emit(first));
  await vi.waitFor(() => expect(createImageBitmap).toHaveBeenCalledWith(first));
  act(() => socket.emit(latest));
  firstDecode.resolve(firstBitmap);

  await vi.waitFor(() => expect(drawImage).toHaveBeenCalledTimes(1));
  expect(createImageBitmap).toHaveBeenLastCalledWith(latest);
  expect(drawImage).toHaveBeenCalledWith(latestBitmap, 0, 0, 1280, 800);
  expect(firstBitmap.close).toHaveBeenCalledOnce();
  expect(latestBitmap.close).toHaveBeenCalledOnce();
});

it("sends critical input immediately and coalesces pointer moves per animation frame", () => {
  const canvas = document.createElement("canvas");
  const canvasRef = { current: canvas };
  const animationFrames: FrameRequestCallback[] = [];
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    animationFrames.push(callback);
    return animationFrames.length;
  });
  const { result } = renderHook(() =>
    useDouyinBrowserSocket({
      loginId: "login-1",
      canvasRef,
    }),
  );
  const socket = FakeWebSocket.instances[0];
  act(() => socket.open());

  act(() => {
    result.current.sendPointer("down", { x: 0.1, y: 0.2 });
    result.current.sendPointer("move", { x: 0.4, y: 0.5 });
    result.current.sendPointer("move", { x: 0.6, y: 0.7 });
    result.current.sendKey("7");
  });

  expect(socket.sent.map((payload) => JSON.parse(payload))).toEqual([
    { type: "pointer", action: "down", x: 0.1, y: 0.2 },
    { type: "key", key: "7" },
  ]);

  act(() => animationFrames[0](16));
  expect(socket.sent.map((payload) => JSON.parse(payload))).toEqual([
    { type: "pointer", action: "down", x: 0.1, y: 0.2 },
    { type: "key", key: "7" },
    { type: "pointer", action: "move", x: 0.6, y: 0.7 },
  ]);
});
