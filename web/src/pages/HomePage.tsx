import { CaretRight, CloudCheck, CloudSlash, FilmStrip, Shuffle, Star, Users } from "@phosphor-icons/react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { archiveMissing, fetchHome, fetchMissingSummary, type FeedItem, type HomeSnapshot } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { routeHref } from "../app/router";
import { formatBytes, formatInteger, greeting } from "../lib/format";
import { useFeed } from "../lib/useFeed";
import { MediaTile, TileSkeleton } from "../media/MediaTile";
import { Player } from "../media/Player";
import { useMediaNavigation } from "../media/useMediaNavigation";
import { sourceLabel } from "../shell/sourceMeta";
import { SourceIcon } from "../shell/SourceIcon";
import { Avatar, ErrorState, Spinner } from "../ui/primitives";
import { FirstSync } from "./FirstSync";

export function HomePage() {
  const { account, toast } = useAppData();
  const [missing, setMissing] = useState<{ missing: number; estimatedBytes: number | null } | null>(null);
  const [queueing, setQueueing] = useState(false);
  const [home, setHome] = useState<HomeSnapshot | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [shelf, setShelf] = useState<{ items: FeedItem[]; index: number } | null>(null);
  const [shuffleSeed, setShuffleSeed] = useState<number | null>(null);
  const [shuffleIndex, setShuffleIndex] = useState(0);
  const shuffle = useFeed(shuffleSeed === null ? null : { sort: "random", seed: shuffleSeed, downloaded: true, limit: 20 });
  const handlers = useMediaNavigation();

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
    if (!missing || !window.confirm(`把 ${formatInteger(missing.missing)} 个作品全部存到 NAS？${missing.estimatedBytes ? `预计需要 ${formatBytes(missing.estimatedBytes)}。` : ""}`)) return;
    setQueueing(true);
    try {
      const result = await archiveMissing();
      toast(result.skipped ? `已加入下载，${result.skipped} 个要等下次同步后才能下载` : "已加入下载队列，可在状态页查看进度");
      setMissing(null);
    } catch {
      toast("加入下载队列失败");
    } finally {
      setQueueing(false);
    }
  }

  const patchShelfItem = useCallback((awemeId: string, patch: Partial<FeedItem>) => {
    const apply = (items: FeedItem[]) => items.map((item) => (item.awemeId === awemeId ? { ...item, ...patch } : item));
    setShelf((current) => (current ? { ...current, items: apply(current.items) } : current));
    setHome((current) => (current ? { ...current, recent: apply(current.recent), starred: apply(current.starred), gone: apply(current.gone) } : current));
  }, []);

  const name = account?.account?.nickname;
  const hello = useMemo(() => greeting(), []);

  if (error) return <ErrorState onRetry={reload} />;
  if (home && home.stats.items === 0) return <FirstSync onReady={reload} />;

  return (
    <>
      <section className="hero">
        <div>
          <h1>
            {hello}
            {name ? `，${name}` : ""}
          </h1>
          <p>{home ? `你的抖音收藏都在这里 · ${formatInteger(home.stats.items)} 个作品` : "正在整理你的收藏…"}</p>
        </div>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!home || home.stats.downloadedItems === 0}
          onClick={() => {
            setShuffleIndex(0);
            setShuffleSeed(1 + Math.floor(Math.random() * 65_000));
          }}
        >
          <Shuffle size={17} weight="bold" />
          随便看看
        </button>
      </section>

      <div className="stats">
        <a className="stat" href={routeHref({ name: "library", filters: {} })}>
          <span>
            <FilmStrip size={15} /> 收藏作品
          </span>
          <strong>{home ? formatInteger(home.stats.items) : "—"}</strong>
          <small>{home ? `视频 ${formatInteger(home.stats.videos)} · 图集 ${formatInteger(home.stats.galleries)}` : " "}</small>
        </a>
        <a className="stat" href={routeHref({ name: "library", filters: { downloaded: true } })}>
          <span>
            <CloudCheck size={15} /> 已存到 NAS
          </span>
          <strong>{home ? formatInteger(home.stats.downloadedItems) : "—"}</strong>
          <small>{home ? `占用 ${formatBytes(home.stats.archivedBytes)}` : " "}</small>
        </a>
        <a className="stat" href={routeHref({ name: "starred", filters: {} })}>
          <span>
            <Star size={15} /> 精选
          </span>
          <strong>{home ? formatInteger(home.stats.starred) : "—"}</strong>
          <small>按 S 键或点星标加入</small>
        </a>
        <a className="stat" href={routeHref({ name: "creators", query: "" })}>
          <span>
            <Users size={15} /> 博主
          </span>
          <strong>{home ? formatInteger(home.stats.creators) : "—"}</strong>
          <small>收藏涉及的创作者</small>
        </a>
        <a className="stat stat-gone" href={routeHref({ name: "gone", filters: {} })}>
          <span>
            <CloudSlash size={15} /> 已在抖音消失
          </span>
          <strong>{home ? formatInteger(home.stats.gone) : "—"}</strong>
          <small>{home ? `已抽查 ${formatInteger(home.stats.remoteChecked)} 个` : " "}</small>
        </a>
      </div>

      {missing && missing.missing > 0 ? (
        <section className="cta">
          <div>
            <strong>还有 {formatInteger(missing.missing)} 个作品没有存到 NAS</strong>
            <p>{missing.estimatedBytes ? `按已下载作品的平均大小估算，大约需要 ${formatBytes(missing.estimatedBytes)}。` : "它们目前只有抖音上的链接，作者删除后就看不到了。"}</p>
          </div>
          <button type="button" className="btn btn-primary btn-sm" disabled={queueing} onClick={() => void downloadMissing()}>
            {queueing ? <Spinner size={14} /> : <CloudCheck size={15} weight="bold" />}
            全部存到 NAS
          </button>
        </section>
      ) : null}

      <section className="section">
        <div className="section-header">
          <h2>最近收藏</h2>
          <a href={routeHref({ name: "library", filters: {} })}>
            全部 <CaretRight size={13} weight="bold" />
          </a>
        </div>
        <div className="shelf">
          {home
            ? home.recent.map((item, index) => (
                <MediaTile key={item.awemeId} item={item} onOpen={() => setShelf({ items: home.recent, index })} onOpenCreator={handlers.openCreator} />
              ))
            : Array.from({ length: 8 }, (_, index) => <TileSkeleton key={index} />)}
        </div>
      </section>

      {home && home.gone.length ? (
        <section className="section">
          <div className="section-header">
            <h2>这些已经从抖音消失了</h2>
            <a href={routeHref({ name: "gone", filters: {} })}>
              全部 <CaretRight size={13} weight="bold" />
            </a>
          </div>
          <div className="shelf">
            {home.gone.map((item, index) => (
              <MediaTile key={item.awemeId} item={item} onOpen={() => setShelf({ items: home.gone, index })} onOpenCreator={handlers.openCreator} />
            ))}
          </div>
        </section>
      ) : null}

      {home && home.starred.length ? (
        <section className="section">
          <div className="section-header">
            <h2>精选</h2>
            <a href={routeHref({ name: "starred", filters: {} })}>
              全部 <CaretRight size={13} weight="bold" />
            </a>
          </div>
          <div className="shelf">
            {home.starred.map((item, index) => (
              <MediaTile key={item.awemeId} item={item} onOpen={() => setShelf({ items: home.starred, index })} onOpenCreator={handlers.openCreator} />
            ))}
          </div>
        </section>
      ) : null}

      {home && home.shelves.length ? (
        <section className="section">
          <div className="section-header">
            <h2>收藏夹与来源</h2>
          </div>
          <div className="collections">
            {home.shelves.map((shelfInfo) => {
              return (
                <a key={shelfInfo.id} className="collection" href={routeHref({ name: "library", sourceId: shelfInfo.id, filters: {} })}>
                  {shelfInfo.covers.length ? (
                    <div className="mosaic">
                      {[0, 1, 2].map((position) => (
                        <MosaicCell key={position} src={shelfInfo.covers[position]} />
                      ))}
                    </div>
                  ) : (
                    <div className="mosaic-empty">
                      <SourceIcon source={shelfInfo} size={34} />
                    </div>
                  )}
                  <strong>
                    <SourceIcon source={shelfInfo} size={16} />
                    {sourceLabel(shelfInfo)}
                  </strong>
                  <small>{formatInteger(shelfInfo.itemCount)} 个作品</small>
                </a>
              );
            })}
          </div>
        </section>
      ) : null}

      {home && home.creators.length ? (
        <section className="section">
          <div className="section-header">
            <h2>收藏最多的博主</h2>
            <a href={routeHref({ name: "creators", query: "" })}>
              全部 <CaretRight size={13} weight="bold" />
            </a>
          </div>
          <div className="people">
            {home.creators.map((creator) => (
              <a key={creator.id} className="person" href={routeHref({ name: "creator", creatorId: creator.id, filters: {} })}>
                <Avatar src={creator.avatarUrl} name={creator.nickname} />
                <strong>{creator.nickname}</strong>
                <small>{formatInteger(creator.itemCount)} 个作品</small>
              </a>
            ))}
          </div>
        </section>
      ) : null}

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
    </>
  );
}

function MosaicCell({ src }: { src?: string }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) return <span />;
  return <img src={src} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />;
}
