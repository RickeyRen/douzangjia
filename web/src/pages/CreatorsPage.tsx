import { CloudArrowDown, Ghost, MagnifyingGlass, Users } from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  archiveCreator,
  fetchCreator,
  fetchCreators,
  recheckCreator,
  refreshCreator,
  updateCreatorSubscription,
  type Creator,
} from "../app/api";
import { useAppData } from "../app/appDataContext";
import { navigate, routeHref, type LibraryFilters, type Route } from "../app/router";
import { ARCHIVE_STATUS_HINT, ARCHIVE_STATUS_LABEL, formerNames, isArchived } from "../lib/creatorArchive";
import { formatCount, formatDate, formatInteger, formatRelative } from "../lib/format";
import { FeedBrowser } from "../media/FeedBrowser";
import { Avatar, EmptyState, ErrorState, PageHeader, Segmented, Spinner, Switch } from "../ui/primitives";
import { t } from "../i18n/t";

export function CreatorsPage({ query }: { query: string }) {
  const [search, setSearch] = useState(query);
  const [sort, setSort] = useState<"items" | "recent">("items");
  const [creators, setCreators] = useState<Creator[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const [debounced, setDebounced] = useState(query);
  const sentinel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    let active = true;
    setCreators(null);
    setError(false);
    fetchCreators({ search: debounced || undefined, sort })
      .then((page) => {
        if (!active) return;
        setCreators(page.items);
        setCursor(page.nextCursor);
      })
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, [debounced, sort, attempt]);

  useEffect(() => {
    const target = sentinel.current;
    if (!target || !cursor || !("IntersectionObserver" in window)) return;
    const observer = new IntersectionObserver(async (entries) => {
      if (!entries.some((entry) => entry.isIntersecting) || loadingMore) return;
      setLoadingMore(true);
      try {
        const page = await fetchCreators({ search: debounced || undefined, sort, cursor });
        setCreators((current) => [...(current ?? []), ...page.items]);
        setCursor(page.nextCursor);
      } finally {
        setLoadingMore(false);
      }
    }, { rootMargin: "600px 0px" });
    observer.observe(target);
    return () => observer.disconnect();
  }, [cursor, debounced, loadingMore, sort]);

  return (
    <>
      <PageHeader title={t("博主")} subtitle="收藏里出现过的所有创作者" />
      <div className="toolbar">
        <form className="search search-inline" onSubmit={(event) => event.preventDefault()}>
          <MagnifyingGlass size={16} weight="bold" />
          <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t("按昵称或抖音号查找")} aria-label={t("查找博主")} />
        </form>
        <Segmented
          label={t("博主排序")}
          value={sort}
          options={[
            { value: "items", label: t("作品最多") },
            { value: "recent", label: t("最近出现") },
          ]}
          onChange={setSort}
        />
      </div>
      {error ? (
        <ErrorState onRetry={() => setAttempt((value) => value + 1)} />
      ) : creators === null ? (
        <div className="state">
          <Spinner size={24} />
        </div>
      ) : creators.length === 0 ? (
        <EmptyState icon={<Users size={40} weight="duotone" />} title={t("没有找到博主")} body={debounced ? t("换个关键词试试。") : undefined} />
      ) : (
        <>
          <div className="creator-grid">
            {creators.map((creator) => (
              <a key={creator.id} className="creator-card" href={routeHref({ name: "creator", creatorId: creator.id, filters: {} })}>
                <Avatar src={creator.avatarUrl} name={creator.nickname} />
                <div>
                  <strong>{creator.nickname}</strong>
                  <small>{creator.uniqueId ? t("抖音号 {id}", { id: creator.uniqueId }) : t("抖音号未知")}</small>
                  <small>
                    {formatInteger(creator.knownItemCount)} 个作品 · 已存 {formatInteger(creator.archivedItemCount)}
                  </small>
                </div>
              </a>
            ))}
          </div>
          <div ref={sentinel} className="grid-footer">
            {loadingMore ? <Spinner /> : null}
          </div>
        </>
      )}
    </>
  );
}

export function CreatorPage({ route }: { route: Extract<Route, { name: "creator" }> }) {
  const { toast } = useAppData();
  const [creator, setCreator] = useState<Creator | null>(null);
  const [error, setError] = useState(false);
  const [queueing, setQueueing] = useState(false);
  const base = useMemo(() => ({ creatorId: route.creatorId }), [route.creatorId]);

  useEffect(() => {
    let active = true;
    setCreator(null);
    setError(false);
    fetchCreator(route.creatorId)
      .then(async (value) => {
        if (!active) return;
        setCreator(value);
        // A removed creator's profile only says what Douyin did to it; keep the archive as is.
        if (!value.uniqueId && !isArchived(value)) {
          // Sparse profiles can be filled in from Douyin; failures just keep what we have.
          const refreshed = await refreshCreator(route.creatorId).catch(() => null);
          if (active && refreshed) setCreator(refreshed);
        }
      })
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, [route.creatorId]);

  async function toggleSubscription(enabled: boolean) {
    if (!creator) return;
    try {
      const subscription = await updateCreatorSubscription(creator.id, enabled);
      setCreator({ ...creator, subscription });
      toast(enabled ? t("会定期收录这位博主的新作品") : t("已停止自动收录"));
    } catch {
      toast(t("设置失败，请稍后重试"));
    }
  }

  async function downloadAll() {
    if (!creator) return;
    setQueueing(true);
    try {
      await archiveCreator(creator.id);
      toast(t("已开始收录这位博主的全部作品"));
    } catch {
      toast(t("收录失败，请检查抖音登录状态"));
    } finally {
      setQueueing(false);
    }
  }

  if (error) return <ErrorState message="找不到这位博主。" onRetry={() => navigate({ name: "creators", query: "" })} />;

  if (creator && isArchived(creator)) {
    return (
      <>
        <ArchiveProfile creator={creator} onChange={setCreator} />
        <FeedBrowser
          base={base}
          filters={route.filters}
          sorts={["published", "archived", "random"]}
          onFiltersChange={(filters: LibraryFilters) => navigate({ ...route, filters }, { replace: true })}
          showMeta={false}
        />
      </>
    );
  }

  const subscribed = Boolean(creator?.subscription?.enabled);
  return (
    <>
      <section className="profile">
        <Avatar src={creator?.avatarUrl} name={creator?.nickname ?? "?"} />
        <div className="profile-body">
          <h1>{creator?.nickname ?? t("加载中…")}</h1>
          <div className="profile-id">{creator?.uniqueId ? t("抖音号 {id}", { id: creator.uniqueId }) : creator ? t("抖音号暂未获取") : " "}</div>
          {creator?.signature ? <p className="profile-signature">{creator.signature}</p> : null}
          {creator && formerNames(creator).length ? (
            <div className="profile-id">{t("曾用名 {names}", { names: formerNames(creator).join("、") })}</div>
          ) : null}
          {creator ? (
            <div className="profile-stats">
              <span>
                <strong>{formatInteger(creator.knownItemCount)}</strong>个收藏作品
              </span>
              <span>
                <strong>{formatInteger(creator.archivedItemCount)}</strong>个已存到 NAS
              </span>
              {creator.followerCount ? (
                <span>
                  <strong>{formatCount(creator.followerCount)}</strong>粉丝
                </span>
              ) : null}
              {creator.postCount ? (
                <span>
                  <strong>{formatCount(creator.postCount)}</strong>个公开作品
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
        {creator ? (
          <div className="profile-actions">
            <label className="chip chip-switch" title={creator.subscription?.lastScanAt ? t("上次检查 {when}", { when: formatRelative(creator.subscription.lastScanAt) }) : undefined}>
              {t("自动收录新作品")}
              <Switch checked={subscribed} onChange={(value) => void toggleSubscription(value)} label={t("自动收录这位博主的新作品")} />
            </label>
            <button type="button" className="btn btn-secondary btn-sm" disabled={queueing} onClick={() => void downloadAll()}>
              {queueing ? <Spinner size={14} /> : <CloudArrowDown size={16} weight="bold" />}
              {t("收录全部作品")}
            </button>
            <a className="btn btn-ghost btn-sm" href={`https://www.douyin.com/user/${creator.id}`} target="_blank" rel="noreferrer">
              {t("抖音主页")}
            </a>
          </div>
        ) : null}
      </section>
      <FeedBrowser
        base={base}
        filters={route.filters}
        sorts={["published", "archived", "random"]}
        onFiltersChange={(filters: LibraryFilters) => navigate({ ...route, filters }, { replace: true })}
        showMeta={false}
      />
    </>
  );
}

function ArchiveProfile({ creator, onChange }: { creator: Creator; onChange: (creator: Creator) => void }) {
  const { toast } = useAppData();
  const [checking, setChecking] = useState(false);
  const [rescuing, setRescuing] = useState(false);
  const archive = creator.archive!;
  const status = archive.status === "active" ? "vanished" : archive.status;
  const kept = archive.preserved;
  const history = (archive.history ?? []).slice().reverse();

  async function recheck() {
    setChecking(true);
    try {
      const next = await recheckCreator(creator.id);
      onChange(next);
      toast(next.archive?.status === "active" ? t("这位博主在抖音上又能看到了") : t("已重新检查，状态没有变化"));
    } catch {
      toast(t("检查失败，请确认抖音登录状态"));
    } finally {
      setChecking(false);
    }
  }

  async function rescue() {
    setRescuing(true);
    try {
      await archiveCreator(creator.id);
      toast(t("已开始抢救这位博主的全部作品"));
    } catch {
      toast(t("抢救失败，作品可能已经无法访问"));
    } finally {
      setRescuing(false);
    }
  }

  const stats: Array<[string, number | null | undefined]> = [
    [t("关注"), kept?.followingCount ?? creator.followingCount],
    [t("粉丝"), kept?.followerCount ?? creator.followerCount],
    [t("获赞"), kept?.totalFavorited ?? creator.totalFavorited],
    [t("作品"), kept?.postCount ?? creator.postCount],
  ];
  return (
    <section className="archive-profile">
      <div className="archive-cover" style={kept?.coverUrl ? { backgroundImage: `url(${kept.coverUrl})` } : undefined}>
        <span className={`archive-ribbon vanished-${status}`}>
          <Ghost size={14} weight="fill" />
          {ARCHIVE_STATUS_LABEL[status]}
          {archive.since ? ` · ${formatDate(archive.since)}` : ""}
        </span>
      </div>
      <div className="archive-head">
        <Avatar src={creator.avatarUrl} name={creator.nickname} />
        <div className="profile-body">
          <h1>{creator.nickname}</h1>
          <div className="profile-id">
            {creator.uniqueId ? t("抖音号 {id}", { id: creator.uniqueId }) : t("抖音号未知")}
            {kept?.ipLocation ?? creator.ipLocation ? ` · ${t("IP 属地 {place}", { place: kept?.ipLocation ?? creator.ipLocation ?? "" })}` : ""}
          </div>
          {kept?.signature ?? creator.signature ? <p className="profile-signature">{kept?.signature ?? creator.signature}</p> : null}
          <div className="profile-stats">
            {stats
              .filter(([, value]) => value)
              .map(([label, value]) => (
                <span key={label}>
                  <strong>{formatCount(value)}</strong>
                  {label}
                </span>
              ))}
          </div>
        </div>
      </div>
      <div className="archive-note">
        <p>{ARCHIVE_STATUS_HINT[status]}</p>
        <p>
          {t("这里显示的是 Ta 原来的资料，最后一次见到是 {date}。现在抖音上显示为「{name}」。", {
            date: formatDate(kept?.lastSeenAt ?? creator.lastSeenAt),
            name: archive.currentNickname,
          })}
        </p>
        <p>
          {t("你收藏过 {known} 个作品，已存到 NAS {saved} 个。", {
            known: formatInteger(creator.knownItemCount),
            saved: formatInteger(creator.archivedItemCount),
          })}
        </p>
        <div className="profile-actions">
          {status === "reset" ? (
            <button type="button" className="btn btn-primary btn-sm" disabled={rescuing} onClick={() => void rescue()}>
              {rescuing ? <Spinner size={14} /> : <CloudArrowDown size={16} weight="bold" />}
              {t("抢救全部作品")}
            </button>
          ) : null}
          <button type="button" className="btn btn-secondary btn-sm" disabled={checking} onClick={() => void recheck()}>
            {checking ? <Spinner size={14} /> : null}
            {t("重新检查")}
          </button>
          <a className="btn btn-ghost btn-sm" href={`https://www.douyin.com/user/${creator.id}`} target="_blank" rel="noreferrer">
            {t("抖音主页")}
          </a>
        </div>
      </div>
      {history.length > 1 ? (
        <ol className="archive-history" aria-label={t("资料变化")}>
          {history.map((snapshot) => (
            <li key={snapshot.id} className={snapshot.degraded ? "is-degraded" : undefined}>
              <Avatar src={snapshot.avatarUrl} name={snapshot.nickname} size={28} />
              <span className="archive-history-name">{snapshot.nickname}</span>
              <small>
                {formatDate(snapshot.firstSeenAt)}
                {snapshot.lastSeenAt !== snapshot.firstSeenAt ? ` – ${formatDate(snapshot.lastSeenAt)}` : ""}
              </small>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
