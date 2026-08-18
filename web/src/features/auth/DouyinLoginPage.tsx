import { QrCode, ShieldCheck } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { beginDouyinLogin, douyinQrUrl, getDouyinLogin, type LoginStatus } from "../../app/api";
import { useI18n } from "../../i18n/context";

export function DouyinLoginPage({ onAuthenticated }: { onAuthenticated?: () => void }) {
  const { t } = useI18n();
  const [status, setStatus] = useState<LoginStatus | null>(null);
  const [error, setError] = useState(false);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (!status || !["starting", "awaiting_scan"].includes(status.state)) return;
    const timer = window.setInterval(() => {
      void getDouyinLogin(status.id)
        .then((next) => {
          setStatus(next);
          if (next.state === "authenticated") onAuthenticated?.();
        })
        .catch(() => setError(true));
    }, 1800);
    return () => window.clearInterval(timer);
  }, [onAuthenticated, status]);

  async function begin() {
    setStarting(true);
    setError(false);
    try {
      setStatus(await beginDouyinLogin());
    } catch {
      setError(true);
    } finally {
      setStarting(false);
    }
  }

  const statusText =
    status?.state === "authenticated"
      ? t("loginSuccess")
      : status?.state === "expired"
        ? t("loginExpired")
        : status?.state === "failed" || error
          ? t("loginFailed")
          : t("awaitingScan");

  return (
    <main className="grid min-h-[100dvh] place-items-center bg-[#0c0e11] px-5 py-12 text-[#f7f8fa]">
      <section className="w-full max-w-[520px] border-t border-white/10 pt-8 text-left">
        <div className="mb-8 flex h-12 w-12 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] shadow-[inset_0_1px_0_rgba(255,255,255,.08)]">
          <QrCode size={25} weight="regular" />
        </div>
        <h1 className="text-3xl font-semibold tracking-[-0.035em]">{t("douyinLoginTitle")}</h1>
        <p className="mt-3 max-w-[46ch] text-[15px] leading-7 text-[#969ba5]">{t("douyinLoginBody")}</p>

        {status?.hasScreenshot ? (
          <div className="mt-8 overflow-hidden rounded-xl border border-white/10 bg-white p-3">
            <img className="mx-auto max-h-[360px] w-auto" src={douyinQrUrl(status.id)} alt={t("qrAlt")} />
          </div>
        ) : null}

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
