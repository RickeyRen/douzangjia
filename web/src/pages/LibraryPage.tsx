import { CloudArrowDown, CloudSlash, Images, MagnifyingGlass, MusicNotes, PencilSimple, Star, Tag, Trash } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";

import {
  archiveSource,
  deleteAlbum,
  fetchCreators,
  renameAlbum,
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
import { t } from "../i18n/t";

type LibraryRoute = Extract<Route, { name: "library" | "starred" | "search" | "album" | "tag" | "gone" }>;

export function LibraryPage({ route }: { route: LibraryRoute }) {
  const { sources } = useAppData();
  const source = route.name === "library" && route.sourceId ? sources.find((entry) => entry.id === route.sourceId) : undefined;
  const sourceId = route.name === "library" ? route.sourceId : undefined;
  const filtersChange = (filters: LibraryFilters) => navigate({ ...route, filters }, { replace: true });

  const searchQuery = route.name === "search" ? route.query : "";
  const albumId = route.name === "album" ? route.albumId : undefined;
  const tag = route.name === "tag" ? route.tag : undefined;
  const base = useMemo(() => {
    if (route.name === "starred") return { starred: true };
    if (route.name === "search") return { search: searchQuery };
    if (route.name === "gone") return { remote: "deleted,private" };
    if (albumId) return { albumId };
    if (tag) return { tag };
    return sourceId ? { sourceId } : {};
  }, [albumId, route.name, searchQuery, sourceId, tag]);

  let sorts: FeedSort[] = ["archived", "published", "random"];
  if (route.name === "search" && searchQuery.trim().split(/\s+/).every((token) => token.length >= 3)) sorts = ["relevance", "archived", "published", "random"];
  if (sourceId) sorts = ["source", "archived", "published", "random"];
  if (route.name === "starred") sorts = ["starred", "archived", "published", "random"];
  if (albumId) sorts = ["album", "archived", "published", "random"];

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
      {route.name === "album" ? (
        <AlbumHeader albumId={route.albumId} />
      ) : route.name === "tag" ? (
        <PageHeader
          title={
            <span className="title-with-icon">
              <Tag size={26} />#{route.tag}
            </span>
          }
          subtitle="带这个标签的作品"
        />
      ) : route.name === "gone" ? (
        <PageHeader
          title={
            <span className="title-with-icon">
              <CloudSlash size={26} />
              {t("已在抖音消失")}
            </span>
          }
          subtitle="抖音上已经删除或设为私密的作品。只要存到了 NAS，这里就永远能看。"
        />
      ) : route.name === "starred" ? (
        <PageHeader title={t("精选")} subtitle="你在抖藏家里标记的作品，只保存在 NAS 上，不会同步到抖音。" />
      ) : route.name === "search" ? (
        <PageHeader title={route.query ? `“${route.query}”` : t("搜索")} subtitle="匹配作品描述、话题、博主、标签和备注；多个词用空格隔开" />
      ) : source ? (
        <SourceHeader source={source} />
      ) : sourceId ? (
        <PageHeader title={t("来源")} />
      ) : (
        <PageHeader title={t("全部作品")} subtitle="所有来源里发现过的作品，已取消收藏的也会永久保留。" />
      )}
      {route.name === "search" && route.query ? <CreatorMatches query={route.query} /> : null}
      <FeedBrowser
        base={base}
        filters={route.filters}
        sorts={sorts}
        onFiltersChange={filtersChange}
        empty={
          route.name === "album" ? (
            <EmptyState icon={<Images size={40} weight="duotone" />} title={t("相册还是空的")} body="播放作品时点「加入相册」，或在网格里多选后批量加入。" />
          ) : route.name === "tag" ? (
            <EmptyState icon={<Tag size={40} weight="duotone" />} title={t("没有带这个标签的作品")} />
          ) : route.name === "gone" ? (
            <EmptyState icon={<CloudSlash size={40} weight="duotone" />} title={t("还没发现消失的作品")} body="抖藏家会在后台慢慢抽查每个作品是否还在抖音上，抽查到的会出现在这里。" />
          ) : route.name === "starred" ? (
            <EmptyState icon={<Star size={40} weight="duotone" />} title={t("还没有精选作品")} body="播放时点星标或按 S 键，就能把喜欢的作品收进这里。" />
          ) : route.name === "search" ? (
            <EmptyState icon={<MagnifyingGlass size={40} weight="duotone" />} title={t("没有找到相关作品")} body="试试更短的关键词，或者博主的抖音号。" />
          ) : undefined
        }
      />
    </>
  );
}

function AlbumHeader({ albumId }: { albumId: number }) {
  const { albums, refreshAlbums, toast } = useAppData();
  const album = albums.find((entry) => entry.id === albumId);
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState("");

  async function submitRename() {
    const value = name.trim();
    if (!album || !value || value === album.name) {
      setRenaming(false);
      return;
    }
    try {
      await renameAlbum(album.id, value);
      await refreshAlbums();
      setRenaming(false);
    } catch {
      toast(t("重命名失败，可能已有同名相册"));
    }
  }

  async function remove() {
    if (!album || !window.confirm(t("删除相册「{name}」？作品本身不会被删除。", { name: album.name }))) return;
    try {
      await deleteAlbum(album.id);
      await refreshAlbums();
      toast(t("相册已删除"));
      navigate({ name: "library", filters: {} }, { replace: true });
    } catch {
      toast(t("删除失败"));
    }
  }

  return (
    <PageHeader
      title={
        renaming ? (
          <form
            className="inline-rename"
            onSubmit={(event) => {
              event.preventDefault();
              void submitRename();
            }}
          >
            <input autoFocus aria-label={t("相册名称")} maxLength={60} value={name} onChange={(event) => setName(event.target.value)} onBlur={() => void submitRename()} onKeyDown={(event) => event.key === "Escape" && setRenaming(false)} />
          </form>
        ) : (
          <span className="title-with-icon">
            <Images size={26} />
            {album?.name ?? t("相册")}
          </span>
        )
      }
      subtitle={album ? t("{n} 个作品 · 只保存在 NAS 上", { n: formatInteger(album.itemCount) }) : " "}
      actions={
        album ? (
          <>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => {
                setName(album.name);
                setRenaming(true);
              }}
            >
              <PencilSimple size={15} weight="bold" />
              {t("重命名")}
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => void remove()}>
              <Trash size={15} weight="bold" />
              {t("删除相册")}
            </button>
          </>
        ) : null
      }
    />
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
      toast(enabled ? t("新作品会自动存到 NAS") : t("已关闭自动下载"));
      void refreshSources();
    } catch {
      setAutoDownload(!enabled);
      toast(t("设置失败，请稍后重试"));
    }
  }

  async function downloadAll() {
    setQueueing(true);
    try {
      await archiveSource(source.id);
      toast(t("已加入下载队列，可在状态页查看进度"));
    } catch {
      toast(t("加入下载队列失败"));
    } finally {
      setQueueing(false);
    }
  }

  const syncNote =
    source.errorCode && source.syncStatus === "failed"
      ? t("上次同步失败：{reason}", { reason: describeError(source.errorCode) ?? "" })
      : t("上次同步 {when}", { when: formatRelative(source.lastIncrementalScanAt ?? source.lastFullScanAt) });
  const entity = ENTITY_SOURCE_KINDS.has(source.kind);

  return (
    <PageHeader
      title={
        <span className="title-with-icon">
          <SourceIcon source={source} size={26} />
          {sourceLabel(source)}
        </span>
      }
      subtitle={`${formatInteger(source.discoveredCount)} ${entity ? t("条目") : t("作品")}${!entity ? t(" · 已存 {n}", { n: formatInteger(source.archivedCount) }) : ""} · ${syncNote}`}
      actions={
        entity ? null : (
          <>
            <label className="chip chip-switch">
              {t("自动存到 NAS")}
              <Switch checked={autoDownload} onChange={(value) => void toggleAuto(value)} label={t("新作品自动存到 NAS")} />
            </label>
            <button type="button" className="btn btn-secondary btn-sm" disabled={queueing} onClick={() => void downloadAll()}>
              {queueing ? <Spinner size={14} /> : <CloudArrowDown size={16} weight="bold" />}
              {t("全部存到 NAS")}
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
    <div className="source-strip" aria-label={t("切换来源")}>
      <a className="chip" href={routeHref({ name: "library", filters: {} })} aria-pressed={routeName === "library" && !activeId}>
        {t("全部")}
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
  if (!entities.length) return <EmptyState icon={<MusicNotes size={40} weight="duotone" />} title={t("这里还没有内容")} />;
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
                  {entity.subtitle || t("收藏的音乐")}
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
            {t("加载更多")}
          </button>
        </div>
      ) : null}
    </>
  );
}
