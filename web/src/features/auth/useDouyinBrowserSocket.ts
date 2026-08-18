import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import type { PointerPoint } from "../../app/api";

export type BrowserTransport = "connecting" | "cdp" | "mjpeg";

type BrowserStatus = {
  type: "status";
  state: string;
  width: number;
  height: number;
  transport: "cdp" | "mjpeg";
};

type Options = {
  loginId?: string;
  canvasRef: RefObject<HTMLCanvasElement | null>;
  onStatus?: (state: string) => void;
};

const RECONNECT_DELAYS = [250, 500, 1_000, 2_000, 5_000] as const;

export function useDouyinBrowserSocket({ loginId, canvasRef, onStatus }: Options) {
  const [transport, setTransport] = useState<BrowserTransport>("connecting");
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const pendingMove = useRef<PointerPoint | null>(null);
  const moveAnimationFrame = useRef<number | null>(null);
  const onStatusRef = useRef(onStatus);
  onStatusRef.current = onStatus;

  useEffect(() => {
    if (!loginId) {
      setConnected(false);
      setTransport("connecting");
      return;
    }

    let stopped = false;
    let fallback = false;
    let retryIndex = 0;
    let reconnectTimer: number | null = null;
    let pendingFrame: Blob | null = null;
    let decoding = false;
    let decodeGeneration = 0;

    setConnected(false);
    setTransport("connecting");

    const drawLatest = async () => {
      if (decoding) return;
      decoding = true;
      const generation = decodeGeneration;
      try {
        while (!stopped && pendingFrame) {
          const candidate = pendingFrame;
          pendingFrame = null;
          const bitmap = await createImageBitmap(candidate);
          if (stopped || generation !== decodeGeneration) {
            bitmap.close();
            return;
          }
          if (pendingFrame) {
            bitmap.close();
            continue;
          }
          const canvas = canvasRef.current;
          const context = canvas?.getContext("2d");
          if (canvas && context) {
            context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
          }
          bitmap.close();
        }
      } catch {
        // A malformed or superseded frame should not break the live connection.
      } finally {
        decoding = false;
        if (!stopped && pendingFrame) void drawLatest();
      }
    };

    const connect = () => {
      if (stopped || fallback) return;
      const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(
        `${scheme}//${window.location.host}/ws/douyin/login/${encodeURIComponent(loginId)}`,
      );
      socketRef.current = socket;
      socket.binaryType = "blob";
      socket.onopen = () => {
        if (stopped) return;
        retryIndex = 0;
        setConnected(true);
      };
      socket.onmessage = (event) => {
        if (typeof event.data === "string") {
          try {
            const status = JSON.parse(event.data) as BrowserStatus;
            if (status.type !== "status") return;
            const canvas = canvasRef.current;
            if (canvas) {
              canvas.width = status.width;
              canvas.height = status.height;
            }
            setTransport(status.transport);
            onStatusRef.current?.(status.state);
            if (status.transport === "mjpeg") fallback = true;
          } catch {
            return;
          }
          return;
        }
        pendingFrame =
          event.data instanceof Blob
            ? event.data
            : new Blob([event.data], { type: "image/jpeg" });
        void drawLatest();
      };
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        if (socketRef.current === socket) socketRef.current = null;
        setConnected(false);
        if (stopped || fallback) return;
        if (retryIndex >= RECONNECT_DELAYS.length) {
          fallback = true;
          setTransport("mjpeg");
          return;
        }
        const delay = RECONNECT_DELAYS[retryIndex];
        retryIndex += 1;
        reconnectTimer = window.setTimeout(connect, delay);
      };
    };

    connect();
    return () => {
      stopped = true;
      decodeGeneration += 1;
      pendingFrame = null;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      const socket = socketRef.current;
      socketRef.current = null;
      socket?.close();
    };
  }, [canvasRef, loginId]);

  const sendNow = useCallback((payload: object) => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(payload));
    }
  }, []);

  const flushMove = useCallback(() => {
    moveAnimationFrame.current = null;
    const point = pendingMove.current;
    pendingMove.current = null;
    if (point) sendNow({ type: "pointer", action: "move", ...point });
  }, [sendNow]);

  const sendPointer = useCallback(
    (action: "down" | "move" | "up", point: PointerPoint) => {
      if (action === "move") {
        pendingMove.current = point;
        if (moveAnimationFrame.current === null) {
          moveAnimationFrame.current = requestAnimationFrame(flushMove);
        }
        return;
      }
      if (pendingMove.current) {
        if (moveAnimationFrame.current !== null) {
          cancelAnimationFrame(moveAnimationFrame.current);
          moveAnimationFrame.current = null;
        }
        flushMove();
      }
      sendNow({ type: "pointer", action, ...point });
    },
    [flushMove, sendNow],
  );

  const sendKey = useCallback(
    (key: string) => sendNow({ type: "key", key }),
    [sendNow],
  );

  return { transport, connected, sendPointer, sendKey };
}
