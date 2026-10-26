import { QrCode, ShieldCheck, X } from "@phosphor-icons/react";
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";

import {
  beginDouyinLogin,
  douyinStreamUrl,
  getDouyinLogin,
  submitDouyinKey,
  submitDouyinPointer,
  type LoginStatus,
  type PointerPoint,
} from "../../app/api";
import { useI18n } from "../../i18n/context";
import { ThemeToggle } from "../../theme/ThemeToggle";
import { useDouyinBrowserSocket } from "./useDouyinBrowserSocket";

export function DouyinLoginPage({ onAuthenticated, onCancel }: { onAuthenticated?: () => void; onCancel?: () => void }) {
  const { t } = useI18n();
  const [status, setStatus] = useState<LoginStatus | null>(null);
  const [error, setError] = useState(false);
  const [starting, setStarting] = useState(false);
  const [interacting, setInteracting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const activePointer = useRef<number | null>(null);
  const fallbackQueue = useRef<Promise<void>>(Promise.resolve());
  const loginId = status?.id;
  const loginState = status?.state;
  const browser = useDouyinBrowserSocket({ loginId, canvasRef });

  useEffect(() => {
    if (!loginId || !loginState || !["starting", "awaiting_scan"].includes(loginState)) return;
    let stopped = false;
    let timer = 0;
    const poll = () => {
      void getDouyinLogin(loginId)
        .then((next) => {
          if (stopped) return;
          setStatus(next);
          if (next.state === "authenticated") onAuthenticated?.();
        })
        .catch(() => {
          if (!stopped) setError(true);
        })
        .finally(() => {
          if (!stopped) timer = window.setTimeout(poll, 1_000);
        });
    };
    timer = window.setTimeout(poll, 1_000);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [loginId, loginState, onAuthenticated]);

  async function begin() {
    setStarting(true);
    setError(false);
    try {
      setStatus(await beginDouyinLogin());
      fallbackQueue.current = Promise.resolve();
    } catch {
      setError(true);
    } finally {
      setStarting(false);
    }
  }

  function forwardPointer(action: "down" | "move" | "up", point: PointerPoint) {
    if (!status) return;
    if (browser.transport !== "mjpeg") {
      browser.sendPointer(action, point);
      return;
    }
    fallbackQueue.current = fallbackQueue.current
      .catch(() => undefined)
      .then(() => submitDouyinPointer(status.id, { action, ...point }))
      .then(() => undefined)
      .catch(() => setError(true));
  }

  function normalizedPoint(event: ReactPointerEvent<HTMLElement>): PointerPoint {
    const bounds = event.currentTarget.getBoundingClientRect();
    const clamp = (value: number) => Math.min(1, Math.max(0, value));
    return {
      x: Number(clamp((event.clientX - bounds.left) / bounds.width).toFixed(4)),
      y: Number(clamp((event.clientY - bounds.top) / bounds.height).toFixed(4)),
    };
  }

  function startDrag(event: ReactPointerEvent<HTMLElement>) {
    if (!status || interacting) return;
    activePointer.current = event.pointerId;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.currentTarget.focus();
    setDragging(true);
    setInteracting(true);
    forwardPointer("down", normalizedPoint(event));
  }

  function continueDrag(event: ReactPointerEvent<HTMLElement>) {
    if (activePointer.current !== event.pointerId) return;
    forwardPointer("move", normalizedPoint(event));
  }

  async function finishDrag(event: ReactPointerEvent<HTMLElement>) {
    if (!status || activePointer.current !== event.pointerId) return;
    activePointer.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    setDragging(false);
    setError(false);
    forwardPointer("up", normalizedPoint(event));
    if (browser.transport === "mjpeg") await fallbackQueue.current;
    setInteracting(false);
  }

  function cancelDrag(event: ReactPointerEvent<HTMLElement>) {
    if (activePointer.current !== event.pointerId) return;
    activePointer.current = null;
    setDragging(false);
    forwardPointer("up", normalizedPoint(event));
    if (browser.transport === "mjpeg") {
      void fallbackQueue.current.finally(() => setInteracting(false));
    } else {
      setInteracting(false);
    }
  }

  function forwardKey(key: string) {
    if (!status) return;
    if (browser.transport !== "mjpeg") {
      browser.sendKey(key);
      return;
    }
    fallbackQueue.current = fallbackQueue.current
      .catch(() => undefined)
      .then(() => submitDouyinKey(status.id, key))
      .then(() => undefined)
      .catch(() => setError(true));
  }

  function handleKeyDown(event: ReactKeyboardEvent<HTMLElement>) {
    const allowed = /^[0-9]$/.test(event.key) || ["Backspace", "Enter", "Tab"].includes(event.key);
    if (!allowed) return;
    event.preventDefault();
    forwardKey(event.key);
  }

  const statusText =
    status?.state === "authenticated"
      ? t("loginSuccess")
      : status?.state === "expired"
        ? t("loginExpired")
        : status?.state === "failed" || error
          ? t("loginFailed")
          : t("awaitingScan");
  const liveStatus =
    browser.transport === "mjpeg"
      ? t("liveFallback")
      : browser.connected
        ? t("liveConnected")
        : t("liveReconnecting");

  if (status?.hasScreenshot) {
    return (
      <main
        className="remote-browser-shell fixed inset-0 overflow-hidden bg-black text-[#f7f8fa]"
        data-testid="douyin-live-view"
      >
        <div className="absolute inset-0 grid place-items-center overflow-hidden">
          {browser.transport === "mjpeg" ? (
            <img
              className={`block max-h-full max-w-full touch-none select-none object-contain ${dragging ? "cursor-grabbing" : "cursor-crosshair"}`}
              src={douyinStreamUrl(status.id)}
              alt={t("qrAlt")}
              draggable={false}
              tabIndex={0}
              onDragStart={(event) => event.preventDefault()}
              onPointerDown={startDrag}
              onPointerMove={continueDrag}
              onPointerUp={(event) => void finishDrag(event)}
              onPointerCancel={cancelDrag}
              onKeyDown={handleKeyDown}
            />
          ) : (
            <canvas
              ref={canvasRef}
              width={1280}
              height={800}
              role="img"
              aria-label={t("qrAlt")}
              className={`block max-h-full max-w-full touch-none select-none object-contain ${dragging ? "cursor-grabbing" : "cursor-crosshair"}`}
              tabIndex={0}
              onPointerDown={startDrag}
              onPointerMove={continueDrag}
              onPointerUp={(event) => void finishDrag(event)}
              onPointerCancel={cancelDrag}
              onKeyDown={handleKeyDown}
            />
          )}
        </div>

        <div className="remote-browser-help">
          <QrCode size={21} weight="regular" />
          <div>
            <p>{t("douyinLoginTitle")}</p>
            <small>{t("dragHint")}</small>
          </div>
        </div>

        {onCancel ? (
          <button type="button" className="friendly-icon-button remote-browser-back" aria-label={t("backToLibrary")} onClick={onCancel}>
            <X size={18} />
          </button>
        ) : null}

        <div className="remote-browser-status-wrap">
          <div className="remote-browser-status" role="status">
            <span />
            {interacting ? t("dragApplying") : `${statusText} · ${liveStatus}`}
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="auth-shell auth-douyin-shell">
      <ThemeToggle className="auth-theme-toggle" />
      <section className="douyin-auth-card">
        <div className="auth-icon">
          <QrCode size={25} weight="regular" />
        </div>
        <h1>{t("douyinLoginTitle")}</h1>
        <p>{t("douyinLoginBody")}</p>

        {status ? (
          <div className="douyin-auth-status" role="status">
            <span />
            {statusText}
          </div>
        ) : null}

        {!status || ["expired", "failed", "cancelled"].includes(status.state) ? (
          <button
            type="button"
            onClick={() => void begin()}
            disabled={starting}
            className="friendly-button friendly-button-primary douyin-auth-button"
          >
            <ShieldCheck size={20} weight="regular" />
            {t("loginDouyin")}
          </button>
        ) : null}
        {onCancel ? (
          <button type="button" onClick={onCancel} className="friendly-button friendly-button-secondary auth-cancel">
            {t("backToLibrary")}
          </button>
        ) : null}
      </section>
    </main>
  );
}
