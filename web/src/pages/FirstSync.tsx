import { Sparkle } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { fetchSyncRuns, triggerSync, type SyncRun } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { formatInteger } from "../lib/format";
import { Progress, Spinner } from "../ui/primitives";
import { t } from "../i18n/t";

/** Shown instead of an empty home while the very first discovery runs. */
export function FirstSync({ onReady }: { onReady: () => void }) {
  const { toast } = useAppData();
  const [run, setRun] = useState<SyncRun | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    let active = true;
    const tick = () =>
      fetchSyncRuns()
        .then((page) => {
          if (!active) return;
          const latest = page.items[0] ?? null;
          setRun(latest);
          if (latest && latest.status === "completed" && latest.discovered > 0) onReady();
        })
        .catch(() => undefined);
    void tick();
    const timer = window.setInterval(tick, 3000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [onReady]);

  async function start() {
    setStarting(true);
    try {
      await triggerSync(true);
      toast(t("已开始整理"));
    } catch {
      toast(t("无法开始同步，请查看状态页"));
    } finally {
      setStarting(false);
    }
  }

  const running = run && ["running", "queued"].includes(run.status);
  return (
    <section className="first-sync" aria-live="polite">
      <span className="first-sync-icon">{running ? <Spinner size={26} /> : <Sparkle size={26} weight="fill" />}</span>
      <h1>{running ? t("正在整理你的收藏") : t("准备好了")}</h1>
      <p>
        {running
          ? t("已发现 {n} 个作品。第一次要把所有收藏夹和账号页从头翻一遍，通常需要十几分钟，你可以先关掉页面。", { n: formatInteger(run?.discovered ?? 0) })
          : run?.status === "failed"
            ? t("第一次同步没有成功，可以重新开始，或者到状态页查看原因。")
            : t("点下面的按钮开始第一次全量同步，抖藏家会把你的收藏夹、喜欢和观看历史都整理进来。")}
      </p>
      {running ? <Progress value={Math.min(95, 5 + Math.log10(1 + (run?.discovered ?? 0)) * 25)} tone="info" /> : (
        <button type="button" className="btn btn-primary" disabled={starting} onClick={() => void start()}>
          {starting ? <Spinner size={16} /> : null}
          {t("开始整理")}
        </button>
      )}
    </section>
  );
}
