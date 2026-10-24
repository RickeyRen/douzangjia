import { CloudArrowDown, MagnifyingGlass, MusicNotes, Star } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";

import {
  archiveSource,
  fetchCreators,
  fetchSourceEntities,
  updateSourceDownloadPolicy,
  type Creator,
  type FeedSort,
  type LibrarySource,
  type SourceEntity,
} from "../app/api";
import { useAppData } from "../app/appDataContext";
import { navigate, routeHref, type LibraryFilters, type Route } from "../app/router";
import { formatInteger, formatRelative } from "../lib/format";
import { describeError } from "../lib/health";
import { FeedBrowser } from "../media/FeedBrowser";
import { ENTITY_SOURCE_KINDS, groupSources, sourceLabel } from "../shell/sourceMeta";
import { SourceIcon } from "../shell/SourceIcon";
import { Avatar, EmptyState, ErrorState, PageHeader, Spinner, Switch } from "../ui/primitives";

type LibraryRoute = Extract<Route, { name: "library" | "starred" | "search" }>;

export function LibraryPage({ route }: { route: LibraryRoute }) {
  const { sources } = useAppData();
  const source = route.name === "library" && route.sourceId ? sources.find((entry) => entry.id === route.sourceId) : undefined;
  const sourceId = route.name === "library" ? route.sourceId : undefined;
  const filtersChange = (filters: LibraryFilters) => navigate({ ...route, filters }, { replace: true });

  const searchQuery = route.name === "search" ? route.query : "";
  const base = useMemo(() => {
    if (route.name === "starred") return { starred: true };
    if (route.name === "search") return { search: searchQuery };
    return sourceId ? { sourceId } : {};
  }, [route.name, searchQuery, sourceId]);

  let sorts: FeedSort[] = ["archived", "published", "random"];
  if (sourceId) sorts = ["source", "archived", "published", "random"];
  if (route.name === "starred") sorts = ["starred", "archived", "published", "random"];

  if (sourceId && source && ENTITY_SOURCE_KINDS.has(source.kind)) {
    return (
      <>
        <SourceHeader source={source} />
        <EntityList sourceId={source.id} />
      </>
    );
  }

  return (
    <>
      <SourceStrip activeId={sourceId} routeName={route.name} />
      {route.name === "starred" ? (
        <PageHeader title="精选" subtitle="你在抖藏家里标记的作品，只保存在 NAS 上，不会同步到抖音。" />
      ) : route.name === "search" ? (
        <PageHeader title={route.query ? `“${route.query}”` : "搜索"} subtitle="匹配作品描述、话题、博主昵称和抖音号" />
      ) : source ? (
        <SourceHeader source={source} />
      ) : sourceId ? (
        <PageHeader title="来源" />
      ) : (
        <PageHeader title="全部作品" subtitle="所有来源里发现过的作品，已取消收藏的也会永久保留。" />
      )}
      {route.name === "search" && route.query ? <CreatorMatches query={route.query} /> : null}
      <FeedBrowser
        base={base}
        filters={route.filters}
        sorts={sorts}
        onFiltersChange={filtersChange}
        empty={
          route.name === "starred" ? (
            <EmptyState icon={<Star size={40} weight="duotone" />} title="还没有精选作品" body="播放时点星标或按 S 键，就能把喜欢的作品收进这里。" />
          ) : route.name === "search" ? (
            <EmptyState icon={<MagnifyingGlass size={40} weight="duotone" />} title="没有找到相关作品" body="试试更短的关键词，或者博主的抖音号。" />
          ) : undefined
        }
      />
    </>
  );
}

function SourceHeader({ source }: { source: LibrarySource }) {
  const { refreshSources, toast } = useAppData();
  const [autoDownload, setAutoDownload] = useState(Boolean(source.autoDownloadEnabled));
  const [queueing, setQueueing] = useState(false);
  useEffect(() => setAutoDownload(Boolean(source.autoDownloadEnabled)), [source.autoDownloadEnabled, source.id]);

  async function toggleAuto(enabled: boolean) {
    setAutoDownload(enabled);
    try {
      await updateSourceDownloadPolicy(source.id, enabled);
      toast(enabled ? "新作品会自动存到 NAS" : "已关闭自动下载");
      void refreshSources();
    } catch {
      setAutoDownload(!enabled);
      toast("设置失败，请稍后重试");
    }
  }

  async function downloadAll() {
    setQueueing(true);
    try {
      await archiveSource(source.id);
      toast("已加入下载队列，可在状态页查看进度");
    } catch {
      toast("加入下载队列失败");
    } finally {
      setQueueing(false);
    }
  }

  const syncNote =
    source.errorCode && source.syncStatus === "failed"
      ? `上次同步失败：${describeError(source.errorCode)}`
      : `上次同步 ${formatRelative(source.lastIncrementalScanAt ?? source.lastFullScanAt)}`;
  const entity = ENTITY_SOURCE_KINDS.has(source.kind);

  return (
    <PageHeader
      title={
        <span className="title-with-icon">
          <SourceIcon source={source} size={26} />
          {sourceLabel(source)}
        </span>
      }
      subtitle={`${formatInteger(source.discoveredCount)} 个${entity ? "条目" : "作品"}${!entity ? ` · 已存 ${formatInteger(source.archivedCount)}` : ""} · ${syncNote}`}
      actions={
        entity ? null : (
          <>
            <label className="chip chip-switch">
              自动存到 NAS
              <Switch checked={autoDownload} onChange={(value) => void toggleAuto(value)} label="新作品自动存到 NAS" />
            </label>
            <button type="button" className="btn btn-secondary btn-sm" disabled={queueing} onClick={() => void downloadAll()}>
              {queueing ? <Spinner size={14} /> : <CloudArrowDown size={16} weight="bold" />}
              全部存到 NAS
            </button>
          </>
        )
      }
    />
  );
}

/** Horizontal source switcher for phones, where the sidebar is hidden. */
function SourceStrip({ activeId, routeName }: { activeId?: string; routeName: string }) {
  const { sources } = useAppData();
  const groups = groupSources(sources);
  const list = [...groups.collections, ...groups.accountActive];
  if (!list.length) return null;
  return (
    <div className="source-strip" aria-label="切换来源">
      <a className="chip" href={routeHref({ name: "library", filters: {} })} aria-pressed={routeName === "library" && !activeId}>
        全部
      </a>
      {list.map((source) => (
        <a key={source.id} className="chip" href={routeHref({ name: "library", sourceId: source.id, filters: {} })} aria-pressed={source.id === activeId}>
          <SourceIcon source={source} size={14} />
          {sourceLabel(source)}
        </a>
      ))}
    </div>
  );
}

function CreatorMatches({ query }: { query: string }) {
  const [creators, setCreators] = useState<Creator[]>([]);
  useEffect(() => {
    let active = true;
    fetchCreators({ search: query, sort: "items" })
      .then((page) => active && setCreators(page.items.slice(0, 12)))
      .catch(() => active && setCreators([]));
    return () => {
      active = false;
    };
  }, [query]);
  if (!creators.length) return null;
  return (
    <section className="matches">
      <div className="people">
        {creators.map((creator) => (
          <a key={creator.id} className="person" href={routeHref({ name: "creator", creatorId: creator.id, filters: {} })}>
            <Avatar src={creator.avatarUrl} name={creator.nickname} />
            <strong>{creator.nickname}</strong>
            <small>{formatInteger(creator.knownItemCount)} 个作品</small>
          </a>
        ))}
      </div>
    </section>
  );
}

function EntityList({ sourceId }: { sourceId: string }) {
  const [entities, setEntities] = useState<SourceEntity[] | null>(null);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    let active = true;
    setEntities(null);
    setError(false);
    fetchSourceEntities({ sourceId })
      .then((page) => {
        if (!active) return;
        setEntities(page.items);
        setCursor(page.nextCursor);
      })
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, [sourceId, attempt]);

  async function more() {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const page = await fetchSourceEntities({ sourceId, cursor });
      setEntities((current) => [...(current ?? []), ...page.items]);
      setCursor(page.nextCursor);
    } finally {
      setLoadingMore(false);
    }
  }

  if (error) return <ErrorState onRetry={() => setAttempt((value) => value + 1)} />;
  if (!entities) return <div className="state"><Spinner size={24} /></div>;
  if (!entities.length) return <EmptyState icon={<MusicNotes size={40} weight="duotone" />} title="这里还没有内容" />;
  return (
    <>
      <div className="entity-grid">
        {entities.map((entity) => {
          const duration = typeof entity.metadata.duration === "string" ? entity.metadata.duration : null;
          const body = (
            <>
              {entity.coverUrl ? <img src={entity.coverUrl} alt="" loading="lazy" referrerPolicy="no-referrer" /> : <span className="entity-cover"><MusicNotes size={24} /></span>}
              <div>
                <strong>{entity.title}</strong>
                <small>
                  {entity.subtitle || "收藏的音乐"}
                  {duration ? ` · ${duration}` : ""}
                </small>
              </div>
            </>
          );
          return entity.sourceUrl ? (
            <a key={entity.id} className="entity" href={entity.sourceUrl} target="_blank" rel="noreferrer">
              {body}
            </a>
          ) : (
            <div key={entity.id} className="entity">
              {body}
            </div>
          );
        })}
      </div>
      {cursor ? (
        <div className="grid-footer">
          <button type="button" className="btn btn-secondary btn-sm" disabled={loadingMore} onClick={() => void more()}>
            {loadingMore ? <Spinner size={14} /> : null}
            加载更多
          </button>
        </div>
      ) : null}
    </>
  );
}
