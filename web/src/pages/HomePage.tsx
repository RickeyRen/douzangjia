import { ArrowClockwise, ArrowUpRight, CalendarBlank, CloudCheck, Ghost, HardDrives, Shuffle, Sparkle, SquaresFour, Users } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import {
  archiveMissing,
  fetchHome,
  fetchMissingSummary,
  triggerSync,
  unqueuedCount,
  type CreatorArchiveStatus,
  type FeedItem,
  type HomeSnapshot,
  type MissingSummary,
} from "../app/api";
import { useAppData } from "../app/appDataContext";
import { routeHref } from "../app/router";
import { ARCHIVE_STATUS_LABEL } from "../lib/creatorArchive";
import { formatBytes, formatInteger, formatRelative } from "../lib/format";
import { refreshArchiveProgress, useArchiveProgress } from "../lib/useArchiveProgress";
import { useFeed } from "../lib/useFeed";
import { MediaTile, TileSkeleton } from "../media/MediaTile";
import { Player } from "../media/Player";
import { useMediaNavigation } from "../media/useMediaNavigation";
import { Avatar, ErrorState, Spinner } from "../ui/primitives";
import { DownloadProgress } from "./DownloadProgress";
import { FirstSync } from "./FirstSync";
import { SavedHeatmap, SpeedChart } from "./HomeCharts";
import { t } from "../i18n/t";

const STATUS_TONE: Record<Exclude<CreatorArchiveStatus, "active">, string> = {
  banned: "st-red",
  reset: "st-amber",
  deactivated: "st-gray",
  vanished: "st-olive",
};

type RecentFilter = "all" | "video" | "gallery";

function weekRange(now = new Date()): string {
  const start = new Date(now.getTime() - 6 * 86_400_000);
  const label = (date: Date) => t("{m}月{d}日", { m: date.getMonth() + 1, d: date.getDate() });
  return `${label(start)} – ${label(now)}`;
}

export function HomePage() {
  const { account, health, refreshHealth, toast } = useAppData();
  const [missing, setMissing] = useState<MissingSummary | null>(null);
  const [queueing, setQueueing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [home, setHome] = useState<HomeSnapshot | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [shelf, setShelf] = useState<{ items: FeedItem[]; index: number } | null>(null);
  const [recentFilter, setRecentFilter] = useState<RecentFilter>("all");
  const [shuffleSeed, setShuffleSeed] = useState<number | null>(null);
  const [shuffleIndex, setShuffleIndex] = useState(0);
  const shuffle = useFeed(shuffleSeed === null ? null : { sort: "random", seed: shuffleSeed, downloaded: true, limit: 20 });
  const handlers = useMediaNavigation();
  const progress = useArchiveProgress();

  useEffect(() => {
    let active = true;
    setError(false);
    fetchHome()
      .then((value) => active && setHome(value))
      .catch(() => active && setError(true));
    fetchMissingSummary()
      .then((value) => active && setMissing(value))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [attempt]);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);

  async function downloadMissing() {
    if (!missing || !window.confirm(t("把 {n} 个收藏作品全部存到 NAS？", { n: formatInteger(unqueuedCount(missing)) }) + (missing.estimatedBytes ? t("预计需要 {size}。", { size: formatBytes(missing.estimatedBytes) }) : ""))) return;
    setQueueing(true);
    try {
      const result = await archiveMissing();
      await refreshArchiveProgress();
      toast(result.skipped ? t("开始下载了，{n} 个要等下次同步后才能下载", { n: result.skipped }) : t("开始下载了，进度会显示在这里"));
      setMissing(null);
    } catch {
      toast(t("加入下载队列失败"));
    } finally {
      setQueueing(false);
    }
  }

  async function syncNow() {
    setSyncing(true);
    try {
      await triggerSync(false);
      toast(t("已开始同步"));
      window.setTimeout(() => void refreshHealth(), 3000);
    } catch {
      toast(t("无法开始同步，请查看状态页"));
    } finally {
      setSyncing(false);
    }
  }

  const patchShelfItem = useCallback((awemeId: string, patch: Partial<FeedItem>) => {
    const apply = (items: FeedItem[]) => items.map((item) => (item.awemeId === awemeId ? { ...item, ...patch } : item));
    setShelf((current) => (current ? { ...current, items: apply(current.items) } : current));
    setHome((current) => (current ? { ...current, recent: apply(current.recent), starred: apply(current.starred), gone: apply(current.gone) } : current));
  }, []);

  const range = useMemo(() => weekRange(), []);
  const recent = useMemo(() => {
    const items = home?.recent ?? [];
    return recentFilter === "all" ? items : items.filter((item) => item.type === recentFilter);
  }, [home, recentFilter]);

  if (error) return <ErrorState onRetry={reload} />;
  if (home && home.stats.items === 0) return <FirstSync onReady={reload} />;

  const stats = home?.stats;
  const week = home?.activity?.week;
  const syncHealth = health ?? home?.health ?? null;
  const nickname = account?.account?.nickname;
  const subtitle = [
    syncHealth?.lastSuccessAt ? t("最后同步 {when}", { when: formatRelative(syncHealth.lastSuccessAt) }) : t("还没有完成过同步"),
    nickname ? t("抖音账号 {name} 已连接", { name: nickname }) : null,
    syncHealth?.intervalSeconds ? t("自动同步每 {m} 分钟一次", { m: Math.round(syncHealth.intervalSeconds / 60) }) : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const savedShare = stats && stats.items ? (stats.downloadedItems / stats.items) * 100 : 0;
  const videoShare = stats && stats.items ? (stats.videos / Math.max(1, stats.videos + stats.galleries)) * 100 : 0;
  const vanishedCount = stats?.vanishedCreators ?? home?.vanishedCreators?.length ?? 0;
  const vanished = home?.vanishedCreators ?? [];
  const topCreators = home?.creators ?? [];
  const topMax = Math.max(1, ...topCreators.map((creator) => creator.itemCount));
  const unqueued = progress && missing ? unqueuedCount(missing) : 0;
  const hasDownloadRow = Boolean(progress && (progress.active || progress.failedTotal > 0)) || unqueued > 0;

  return (
    <div className="overview">
      <header className="ov-head">
        <div>
          <h1>{t("存档总览")}</h1>
          <p>{home ? subtitle : t("正在整理你的收藏…")}</p>
        </div>
        <div className="ov-actions">
          <span className="ghost-chip" title={t("卡片上的增长数字按最近 7 天计算")}>
            <CalendarBlank size={15} />
            {range}
          </span>
          <button
            type="button"
            className="ghost-chip is-button"
            disabled={!home || home.stats.downloadedItems === 0}
            onClick={() => {
              setShuffleIndex(0);
              setShuffleSeed(1 + Math.floor(Math.random() * 65_000));
            }}
          >
            <Shuffle size={15} />
            {t("随便看看")}
          </button>
          <button type="button" className="btn btn-primary btn-glow" disabled={syncing} onClick={() => void syncNow()}>
            {syncing ? <Spinner size={14} /> : <ArrowClockwise size={15} weight="bold" />}
            {t("立即同步")}
          </button>
        </div>
      </header>

      <section className="bento kpis" aria-label={t("存档统计")}>
        <KpiCard
          href={routeHref({ name: "library", filters: {} })}
          icon={<SquaresFour size={15} />}
          label={t("收藏作品")}
          value={stats ? formatInteger(stats.items) : "—"}
          pill={week?.items ? <span className="pill up">+{formatInteger(week.items)}</span> : null}
          sub={stats ? t("视频 {videos} · 图集 {galleries}", { videos: formatInteger(stats.videos), galleries: formatInteger(stats.galleries) }) : " "}
        >
          <div className="split" aria-hidden="true">
            <i style={{ width: `${videoShare}%` }} />
            <i style={{ width: `${100 - videoShare}%` }} />
          </div>
        </KpiCard>
        <KpiCard
          href={routeHref({ name: "library", filters: { downloaded: true } })}
          icon={<HardDrives size={15} />}
          label={t("已存到 NAS")}
          value={stats ? formatInteger(stats.downloadedItems) : "—"}
          pill={week?.saved ? <span className="pill up">+{formatInteger(week.saved)}</span> : null}
          sub={stats ? t("占用 {size} · 占收藏 {p}%", { size: formatBytes(stats.archivedBytes), p: savedShare.toFixed(1) }) : " "}
        >
          <div className="bar" aria-hidden="true">
            <i style={{ width: `${Math.min(100, savedShare)}%` }} />
          </div>
        </KpiCard>
        <KpiCard
          href={routeHref({ name: "creators", query: "" })}
          icon={<Users size={15} />}
          label={t("博主")}
          value={stats ? formatInteger(stats.creators) : "—"}
          pill={week?.creators ? <span className="pill olive">+{formatInteger(week.creators)}</span> : null}
          sub={topCreators[0] ? t("收藏最多：{name} {n} 个", { name: topCreators[0].nickname, n: formatInteger(topCreators[0].itemCount) }) : t("收藏涉及的创作者")}
        >
          <div className="ticks" aria-hidden="true">
            {topCreators.slice(0, 14).map((creator, index) => (
              <i key={creator.id} className={index < 3 ? (index === 0 ? "is-top" : "is-hi") : undefined} style={{ height: `${Math.max(3, Math.round((creator.itemCount / topMax) * 20))}px` }} />
            ))}
          </div>
        </KpiCard>
        <KpiCard
          href={routeHref({ name: "vanished" })}
          icon={<Ghost size={15} />}
          label={t("已在抖音消失")}
          value={stats ? formatInteger(vanishedCount) : "—"}
          unit={t("位")}
          pill={week?.vanished ? <span className="pill down">+{formatInteger(week.vanished)}</span> : null}
          sub={vanishedCount ? t("原来的头像、昵称和作品都已留档") : t("还没有博主从抖音消失")}
        >
          {vanished.length ? (
            <div className="avs" aria-hidden="true">
              {vanished.slice(0, 5).map((creator) => (
                <span key={creator.id} className="gone-av">
                  <Avatar src={creator.avatarUrl} name={creator.nickname} size={26} />
                </span>
              ))}
              {vanishedCount > 5 ? <span className="more">+{formatInteger(vanishedCount - 5)}</span> : null}
            </div>
          ) : null}
        </KpiCard>
      </section>

      {hasDownloadRow ? (
        <section className="dl-row" aria-label={t("下载")}>
          {progress ? <DownloadProgress progress={progress} variant="home" /> : null}
          {unqueued > 0 && missing ? (
            <section className="card dl-card dl-act">
              <span className="act-l">
                <Sparkle size={13} weight="fill" />
                {t("待存档")}
              </span>
              <h3>
                {t("还有")} <b className="num">{formatInteger(unqueued)}</b> {t("个收藏作品没有存到 NAS")}
              </h3>
              <p>{missing.estimatedBytes ? t("按已存作品的平均大小估算，约 {size}", { size: formatBytes(missing.estimatedBytes) }) : t("它们目前只有抖音上的链接，作者删除后就看不到了")}</p>
              <button type="button" className="btn-w" disabled={queueing} onClick={() => void downloadMissing()}>
                {queueing ? <Spinner size={14} /> : <CloudCheck size={16} weight="bold" />}
                {t("全部存到 NAS")}
                <ArrowUpRight size={14} weight="bold" />
              </button>
            </section>
          ) : null}
        </section>
      ) : null}

      <section className="bento charts">
        <SpeedChart activity={home?.activity} currentBps={progress?.active && progress.active.status !== "paused" ? progress.active.speedBps : null} />
        <SavedHeatmap activity={home?.activity} />
      </section>

      <section className="bento lists">
        <section className="card gonec" aria-label={t("已在抖音消失的博主")}>
          <div className="row-h top">
            <div>
              <h2 className="h4">{t("已在抖音消失的博主")}</h2>
              <p className="cap">{t("Ta 原来的样子，这里还留着")}</p>
            </div>
            <span className="sp" />
            <a className="pill down" href={routeHref({ name: "vanished" })}>
              {t("{n} 位", { n: formatInteger(vanishedCount) })}
            </a>
          </div>
          {vanished.length ? (
            <ul className="glist">
              {vanished.slice(0, 5).map((creator) => (
                <li key={creator.id}>
                  <a href={routeHref({ name: "creator", creatorId: creator.id, filters: {} })}>
                    <span className="gone-av">
                      <Avatar src={creator.avatarUrl} name={creator.nickname} size={36} />
                    </span>
                    <div>
                      <b>{creator.nickname}</b>
                      <span>{t("留档 {n} 个作品", { n: formatInteger(creator.itemCount) })}</span>
                    </div>
                    {creator.status !== "active" ? <span className={`st ${STATUS_TONE[creator.status]}`}>{ARCHIVE_STATUS_LABEL[creator.status]}</span> : null}
                  </a>
                </li>
              ))}
            </ul>
          ) : (
            <p className="gone-empty">{home ? t("还没有发现被封禁、注销或清空作品的博主。抖藏家会每天检查一遍。") : " "}</p>
          )}
        </section>

        <section className="card recc">
          <div className="row-h top">
            <div>
              <h2 className="h4">{t("最近收藏")}</h2>
              <p className="cap">{week ? t("最近 7 天新增 {n} 个 · 存到 NAS {saved} 个", { n: formatInteger(week.items), saved: formatInteger(week.saved) }) : t("最新发现的收藏作品")}</p>
            </div>
            <span className="sp" />
            <div className="mini-seg" role="group" aria-label={t("作品类型")}>
              {(
                [
                  ["all", t("全部")],
                  ["video", t("视频")],
                  ["gallery", t("图集")],
                ] as Array<[RecentFilter, string]>
              ).map(([value, label]) => (
                <button key={value} type="button" aria-pressed={recentFilter === value} onClick={() => setRecentFilter(value)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="rec">
            {home
              ? recent.slice(0, 12).map((item) => (
                  <MediaTile key={item.awemeId} item={item} onOpen={() => setShelf({ items: recent, index: recent.indexOf(item) })} onOpenCreator={handlers.openCreator} />
                ))
              : Array.from({ length: 6 }, (_, index) => <TileSkeleton key={index} />)}
            {home && recent.length === 0 ? <p className="gone-empty">{t("最近没有这类作品")}</p> : null}
          </div>
        </section>
      </section>

      {shelf ? (
        <Player
          items={shelf.items}
          index={shelf.index}
          onIndexChange={(index) => setShelf((current) => (current ? { ...current, index } : current))}
          onClose={() => setShelf(null)}
          onItemPatch={patchShelfItem}
          {...handlers.playerProps(() => setShelf(null))}
        />
      ) : null}

      {shuffleSeed !== null && (shuffle.items.length > 0 || shuffle.loading) ? (
        <Player
          items={shuffle.items}
          index={shuffleIndex}
          onIndexChange={setShuffleIndex}
          onClose={() => setShuffleSeed(null)}
          hasMore={shuffle.hasMore}
          onLoadMore={() => void shuffle.loadMore()}
          onItemPatch={shuffle.updateItem}
          {...handlers.playerProps(() => setShuffleSeed(null))}
        />
      ) : null}
    </div>
  );
}

function KpiCard({ href, icon, label, value, unit, pill, sub, children }: { href: string; icon: ReactNode; label: string; value: string; unit?: string; pill: ReactNode; sub: string; children?: ReactNode }) {
  return (
    <a className="card kpi" href={href}>
      <div className="kpi-h">
        <span className="chip-ic">{icon}</span>
        <span className="kpi-l">{label}</span>
        <span className="circ" aria-hidden="true">
          <ArrowUpRight size={13} />
        </span>
      </div>
      <div className="kpi-n">
        <span className="num big">{value}</span>
        {unit ? <span className="kpi-u">{unit}</span> : null}
        {pill}
      </div>
      <div className="kpi-s">{sub}</div>
      {children}
    </a>
  );
}
