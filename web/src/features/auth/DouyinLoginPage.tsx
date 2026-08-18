import { QrCode, ShieldCheck } from "@phosphor-icons/react";
import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";

import {
  beginDouyinLogin,
  douyinStreamUrl,
  getDouyinLogin,
  submitDouyinPointer,
  type LoginStatus,
  type PointerPoint,
} from "../../app/api";
import { useI18n } from "../../i18n/context";

export function DouyinLoginPage({ onAuthenticated }: { onAuthenticated?: () => void }) {
  const { t } = useI18n();
  const [status, setStatus] = useState<LoginStatus | null>(null);
  const [error, setError] = useState(false);
  const [starting, setStarting] = useState(false);
  const [interacting, setInteracting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const activePointer = useRef<number | null>(null);
  const pointerQueue = useRef<Promise<void>>(Promise.resolve());
  const lastMoveAt = useRef(0);
  const loginId = status?.id;
  const loginState = status?.state;

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
    timer = window.setTimeout(poll, 250);
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
      pointerQueue.current = Promise.resolve();
    } catch {
      setError(true);
    } finally {
      setStarting(false);
    }
  }

  function forwardPointer(action: "down" | "move" | "up", point: PointerPoint) {
    if (!status) return;
    const id = status.id;
    pointerQueue.current = pointerQueue.current
      .catch(() => undefined)
      .then(() => submitDouyinPointer(id, { action, ...point }))
      .then(() => undefined)
      .catch(() => setError(true));
  }

  function normalizedPoint(event: ReactPointerEvent<HTMLImageElement>): PointerPoint {
    const bounds = event.currentTarget.getBoundingClientRect();
    const clamp = (value: number) => Math.min(1, Math.max(0, value));
    return {
      x: Number(clamp((event.clientX - bounds.left) / bounds.width).toFixed(4)),
      y: Number(clamp((event.clientY - bounds.top) / bounds.height).toFixed(4)),
    };
  }

  function startDrag(event: ReactPointerEvent<HTMLImageElement>) {
    if (!status || interacting) return;
    activePointer.current = event.pointerId;
    lastMoveAt.current = 0;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setDragging(true);
    setInteracting(true);
    forwardPointer("down", normalizedPoint(event));
  }

  function continueDrag(event: ReactPointerEvent<HTMLImageElement>) {
    if (activePointer.current !== event.pointerId) return;
    if (lastMoveAt.current && event.timeStamp - lastMoveAt.current < 50) return;
    lastMoveAt.current = event.timeStamp;
    forwardPointer("move", normalizedPoint(event));
  }

  async function finishDrag(event: ReactPointerEvent<HTMLImageElement>) {
    if (!status || activePointer.current !== event.pointerId) return;
    activePointer.current = null;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    setDragging(false);
    setError(false);
    forwardPointer("up", normalizedPoint(event));
    await pointerQueue.current;
    setInteracting(false);
  }

  function cancelDrag(event: ReactPointerEvent<HTMLImageElement>) {
    if (activePointer.current !== event.pointerId) return;
    activePointer.current = null;
    setDragging(false);
    forwardPointer("up", normalizedPoint(event));
    void pointerQueue.current.finally(() => setInteracting(false));
  }

  const statusText =
    status?.state === "authenticated"
      ? t("loginSuccess")
      : status?.state === "expired"
        ? t("loginExpired")
        : status?.state === "failed" || error
          ? t("loginFailed")
          : t("awaitingScan");

  if (status?.hasScreenshot) {
    return (
      <main
        className="fixed inset-0 overflow-hidden bg-black text-[#f7f8fa]"
        data-testid="douyin-live-view"
      >
        <div className="absolute inset-0 grid place-items-center overflow-hidden">
          <img
            className={`block max-h-full max-w-full touch-none select-none object-contain ${dragging ? "cursor-grabbing" : "cursor-crosshair"}`}
            src={douyinStreamUrl(status.id)}
            alt={t("qrAlt")}
            draggable={false}
            onDragStart={(event) => event.preventDefault()}
            onPointerDown={startDrag}
            onPointerMove={continueDrag}
            onPointerUp={(event) => void finishDrag(event)}
            onPointerCancel={cancelDrag}
          />
        </div>

        <div className="pointer-events-none absolute left-4 top-4 flex items-center gap-3 rounded-xl border border-white/10 bg-[#0c0e11]/85 px-4 py-3 shadow-2xl backdrop-blur-xl">
          <QrCode size={21} weight="regular" />
          <div>
            <p className="text-sm font-semibold">{t("douyinLoginTitle")}</p>
            <p className="mt-0.5 text-[11px] text-[#a7abb3]">{t("dragHint")}</p>
          </div>
        </div>

        <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center px-4">
          <div className="flex items-center gap-3 rounded-full border border-white/10 bg-[#0c0e11]/85 px-4 py-2.5 text-sm text-[#d7dae0] shadow-2xl backdrop-blur-xl" role="status">
            <span className="h-2 w-2 rounded-full bg-[#f16761] motion-safe:animate-pulse" />
            {interacting ? t("dragApplying") : statusText}
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="grid min-h-[100dvh] place-items-center bg-[#0c0e11] px-5 py-12 text-[#f7f8fa]">
      <section className="w-full max-w-[520px] border-t border-white/10 pt-8 text-left">
        <div className="mb-8 flex h-12 w-12 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] shadow-[inset_0_1px_0_rgba(255,255,255,.08)]">
          <QrCode size={25} weight="regular" />
        </div>
        <h1 className="text-3xl font-semibold tracking-[-0.035em]">{t("douyinLoginTitle")}</h1>
        <p className="mt-3 max-w-[46ch] text-[15px] leading-7 text-[#969ba5]">{t("douyinLoginBody")}</p>

        {status ? (
          <div className="mt-5 flex items-center gap-3 text-sm text-[#b8bcc4]" role="status">
            <span className="h-2 w-2 rounded-full bg-[#f16761] motion-safe:animate-pulse" />
            {statusText}
          </div>
        ) : null}

        {!status || ["expired", "failed", "cancelled"].includes(status.state) ? (
          <button
            type="button"
            onClick={() => void begin()}
            disabled={starting}
            className="mt-8 inline-flex min-h-12 items-center gap-2 rounded-lg bg-[#f16761] px-5 text-sm font-semibold text-[#141518] transition-transform duration-200 active:scale-[.98] disabled:opacity-50"
          >
            <ShieldCheck size={20} weight="regular" />
            {t("loginDouyin")}
          </button>
        ) : null}
      </section>
    </main>
  );
}
