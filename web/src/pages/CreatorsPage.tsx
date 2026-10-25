import { CloudArrowDown, MagnifyingGlass, Users } from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  archiveCreator,
  fetchCreator,
  fetchCreators,
  refreshCreator,
  updateCreatorSubscription,
  type Creator,
} from "../app/api";
import { useAppData } from "../app/appDataContext";
import { navigate, routeHref, type LibraryFilters, type Route } from "../app/router";
import { formatCount, formatInteger, formatRelative } from "../lib/format";
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
        if (!value.uniqueId) {
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

  const subscribed = Boolean(creator?.subscription?.enabled);
  return (
    <>
      <section className="profile">
        <Avatar src={creator?.avatarUrl} name={creator?.nickname ?? "?"} />
        <div className="profile-body">
          <h1>{creator?.nickname ?? t("加载中…")}</h1>
          <div className="profile-id">{creator?.uniqueId ? t("抖音号 {id}", { id: creator.uniqueId }) : creator ? t("抖音号暂未获取") : " "}</div>
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
