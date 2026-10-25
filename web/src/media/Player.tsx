import {
  ArrowSquareOut,
  CaretDown,
  CaretLeft,
  CaretRight,
  CaretUp,
  CloudArrowDown,
  DownloadSimple,
  Info,
  LinkSimple,
  Repeat,
  SpeakerHigh,
  SpeakerSlash,
  Star,
  X,
  ArrowClockwise,
} from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState, type TouchEvent, type WheelEvent } from "react";

import { archiveItem, checkRemoteAvailability, type FeedItem, type RemoteAvailability } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { formatBytes, formatCount, formatDate, formatDuration } from "../lib/format";
import { Avatar, Spinner } from "../ui/primitives";
import { AddToAlbumButton, NoteEditor, TagEditor } from "./Organize";
import { VideoControls } from "./VideoControls";
import { douyinUrl, itemDurationMs, itemTitle, thumbnailCandidates } from "./itemInfo";
import { t } from "../i18n/t";

const MUTED_KEY = "douzangjia.player.muted";
const AUTOPLAY_KEY = "douzangjia.player.autonext";
const PANEL_KEY = "douzangjia.player.panel";

function readFlag(key: string, fallback: boolean): boolean {
  try {
    const value = window.localStorage.getItem(key);
    return value === null ? fallback : value === "1";
  } catch {
    return fallback;
  }
}

function writeFlag(key: string, value: boolean) {
  try {
    window.localStorage.setItem(key, value ? "1" : "0");
  } catch {
    // Preferences are a convenience; playback works without storage.
  }
}

const isDesktop = () => typeof window !== "undefined" && window.matchMedia?.("(min-width: 901px)").matches !== false;

const REMOTE_LABEL: Record<RemoteAvailability["status"], { text: string; tone: string }> = {
  available: { text: t("抖音上仍可访问"), tone: "badge-success" },
  deleted: { text: t("抖音上已删除"), tone: "badge-danger" },
  private: { text: t("已设为私密"), tone: "badge-warning" },
  restricted: { text: t("访问受限"), tone: "badge-warning" },
  auth_required: { text: t("需要登录才能查看"), tone: "badge-warning" },
  rate_limited: { text: t("检查过于频繁"), tone: "badge-warning" },
  unknown: { text: t("尚未检查"), tone: "" },
};

export type PlayerProps = {
  items: FeedItem[];
  index: number;
  onIndexChange: (index: number) => void;
  onClose: () => void;
  hasMore?: boolean;
  onLoadMore?: () => void;
  onItemPatch?: (awemeId: string, patch: Partial<FeedItem>) => void;
  onOpenCreator?: (creatorId: string | null, name: string) => void;
  onSearch?: (term: string) => void;
  onOpenSource?: (sourceId: string) => void;
  onOpenAlbum?: (albumId: number) => void;
  onOpenTag?: (tag: string) => void;
};

export function Player({
  items,
  index,
  onIndexChange,
  onClose,
  hasMore = false,
  onLoadMore,
  onItemPatch,
  onOpenCreator,
  onSearch,
  onOpenSource,
  onOpenAlbum,
  onOpenTag,
}: PlayerProps) {
  const { toggleStar, toast } = useAppData();
  const item = items[index];
  const [muted, setMuted] = useState(() => readFlag(MUTED_KEY, false));
  const [autoNext, setAutoNext] = useState(() => readFlag(AUTOPLAY_KEY, true));
  const [panelOpen, setPanelOpen] = useState(() => isDesktop() && readFlag(PANEL_KEY, true));
  const [imageIndex, setImageIndex] = useState(0);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [idle, setIdle] = useState(false);
  const idleTimer = useRef<number | undefined>(undefined);
  const wheelLock = useRef(0);
  const touchStart = useRef<{ x: number; y: number } | null>(null);

  const images = item ? item.media.filter((media) => media.type === "image") : [];
  const video = item?.media.find((media) => media.type === "video");
  const atStart = index <= 0;
  const atEnd = index >= items.length - 1 && !hasMore;

  const go = useCallback(
    (direction: -1 | 1) => {
      const next = index + direction;
      if (next < 0) return;
      if (next >= items.length) {
        if (hasMore) onLoadMore?.();
        return;
      }
      onIndexChange(next);
    },
    [hasMore, index, items.length, onIndexChange, onLoadMore],
  );

  useEffect(() => setImageIndex(0), [item?.awemeId]);

  useEffect(() => {
    if (hasMore && index >= items.length - 3) onLoadMore?.();
  }, [hasMore, index, items.length, onLoadMore]);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  // Warm the next poster so swiping feels instant.
  useEffect(() => {
    const next = items[index + 1];
    const src = next ? thumbnailCandidates(next)[0] : undefined;
    if (src) {
      const image = new Image();
      image.src = src;
    }
  }, [index, items]);

  const star = useCallback(async () => {
    if (!item) return;
    const result = await toggleStar(item);
    if (result !== null) onItemPatch?.(item.awemeId, { starred: result });
  }, [item, onItemPatch, toggleStar]);

  const wake = useCallback(() => {
    setIdle(false);
    window.clearTimeout(idleTimer.current);
    idleTimer.current = window.setTimeout(() => setIdle(true), 2400);
  }, []);

  useEffect(() => {
    wake();
    return () => window.clearTimeout(idleTimer.current);
  }, [wake, item?.awemeId]);

  const toggleMute = useCallback(() => {
    setMuted((value) => {
      writeFlag(MUTED_KEY, !value);
      return !value;
    });
  }, []);

  const togglePanel = useCallback(() => {
    setPanelOpen((value) => {
      writeFlag(PANEL_KEY, !value);
      return !value;
    });
  }, []);

  /** Turns the gallery page; returns false at either end so the caller can change item. */
  const stepImage = useCallback(
    (direction: -1 | 1) => {
      const next = imageIndex + direction;
      if (images.length < 2 || next < 0 || next >= images.length) return false;
      setImageIndex(next);
      return true;
    },
    [imageIndex, images.length],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      switch (event.key) {
        case "Escape":
          event.preventDefault();
          onClose();
          break;
        case "ArrowDown":
        case "j":
        case "J":
          event.preventDefault();
          go(1);
          break;
        case "ArrowUp":
        case "k":
        case "K":
          event.preventDefault();
          go(-1);
          break;
        case "ArrowRight":
          event.preventDefault();
          if (!stepImage(1)) go(1);
          break;
        case "ArrowLeft":
          event.preventDefault();
          if (!stepImage(-1)) go(-1);
          break;
        case " ": {
          const element = videoRef.current;
          if (!element) break;
          event.preventDefault();
          if (element.paused) void element.play().catch(() => undefined);
          else element.pause();
          break;
        }
        case "m":
        case "M":
          toggleMute();
          break;
        case "s":
        case "S":
          void star();
          break;
        case "i":
        case "I":
          togglePanel();
          break;
        case "f":
        case "F":
          if (document.fullscreenElement) void document.exitFullscreen().catch(() => undefined);
          else void document.documentElement.requestFullscreen?.().catch(() => undefined);
          break;
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, onClose, star, stepImage, toggleMute, togglePanel]);

  function onWheel(event: WheelEvent) {
    if (Math.abs(event.deltaY) < 24) return;
    const now = Date.now();
    if (now - wheelLock.current < 650) return;
    wheelLock.current = now;
    go(event.deltaY > 0 ? 1 : -1);
  }

  function onTouchStart(event: TouchEvent) {
    const touch = event.touches[0];
    touchStart.current = { x: touch.clientX, y: touch.clientY };
  }

  function onTouchEnd(event: TouchEvent) {
    const start = touchStart.current;
    touchStart.current = null;
    if (!start) return;
    const touch = event.changedTouches[0];
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.abs(dy) > 60 && Math.abs(dy) > Math.abs(dx) * 1.2) go(dy < 0 ? 1 : -1);
    else if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) stepImage(dx < 0 ? 1 : -1);
  }

  async function copyLink() {
    if (!item) return;
    try {
      await navigator.clipboard.writeText(douyinUrl(item));
      toast(t("已复制抖音链接"));
    } catch {
      toast(t("复制失败"));
    }
  }

  async function downloadNow() {
    if (!item) return;
    try {
      await archiveItem(item.awemeId);
      onItemPatch?.(item.awemeId, { local: { ...item.local, state: "waiting" } });
      toast(t("已加入下载队列"));
    } catch {
      toast(t("加入下载队列失败"));
    }
  }

  if (!item) {
    return (
      <div className="player" role="dialog" aria-modal="true" aria-label={t("播放器")}>
        <div className="player-stage">
          <Spinner size={28} />
        </div>
      </div>
    );
  }

  const name = item.creator?.nickname || item.author;
  const backdrop = thumbnailCandidates(item)[0];
  const downloaded = item.local.state === "downloaded";

  return (
    <div className="player" role="dialog" aria-modal="true" aria-label={t("播放：{title}", { title: itemTitle(item) })}>
      <div className={`player-stage${idle ? " is-idle" : ""}`} onWheel={onWheel} onTouchStart={onTouchStart} onTouchEnd={onTouchEnd} onPointerMove={wake} onPointerDown={wake}>
        {backdrop ? <div className="player-backdrop" style={{ backgroundImage: `url("${backdrop}")` }} /> : null}

        <div className="player-media">
          {video && downloaded ? (
            <video
              key={video.url}
              ref={videoRef}
              src={video.url}
              poster={video.posterUrl}
              autoPlay
              playsInline
              muted={muted}
              onClick={(event) => {
                const element = event.currentTarget;
                if (element.paused) void element.play().catch(() => undefined);
                else element.pause();
              }}
              loop={!autoNext}
              onVolumeChange={(event) => {
                const element = event.currentTarget;
                if (element.muted !== muted) {
                  setMuted(element.muted);
                  writeFlag(MUTED_KEY, element.muted);
                }
              }}
              onEnded={() => {
                if (autoNext && !atEnd) go(1);
              }}
            />
          ) : images.length > 0 ? (
            <img key={images[imageIndex]?.url} src={images[imageIndex]?.url} alt={itemTitle(item)} draggable={false} />
          ) : (
            <div className="player-empty">
              {backdrop ? <img src={backdrop} alt="" referrerPolicy="no-referrer" /> : null}
              <p>{item.local.state === "failed" ? t("这个作品下载失败了。") : t("这个作品还没有下载到 NAS。")}</p>
              <div className="player-empty-actions">
                <button type="button" className="btn btn-primary btn-sm" onClick={() => void downloadNow()}>
                  <CloudArrowDown size={16} weight="bold" />
                  {item.local.state === "failed" ? t("重新下载") : t("立即下载")}
                </button>
                <a className="btn btn-secondary btn-sm" href={douyinUrl(item)} target="_blank" rel="noreferrer">
                  <ArrowSquareOut size={16} weight="bold" />
                  {t("在抖音打开")}
                </a>
              </div>
            </div>
          )}
        </div>

        {video && downloaded ? <VideoControls videoRef={videoRef} muted={muted} onToggleMute={toggleMute} /> : null}

        {images.length > 1 ? (
          <>
            <button type="button" className="icon-btn player-glass gallery-arrow is-prev" aria-label={t("上一张")} disabled={imageIndex === 0} onClick={() => stepImage(-1)}>
              <CaretLeft size={20} weight="bold" />
            </button>
            <button type="button" className="icon-btn player-glass gallery-arrow is-next" aria-label={t("下一张")} disabled={imageIndex === images.length - 1} onClick={() => stepImage(1)}>
              <CaretRight size={20} weight="bold" />
            </button>
            <div className="gallery-dots" aria-label={t("第 {current} 张，共 {total} 张", { current: imageIndex + 1, total: images.length })}>
              {images.map((image, position) => (
                <span key={image.id} className={position === imageIndex ? "is-active" : undefined} />
              ))}
            </div>
          </>
        ) : null}

        <div className="player-top">
          <button type="button" className="icon-btn player-glass" aria-label={t("关闭播放器")} onClick={onClose}>
            <X size={20} weight="bold" />
          </button>
          <span className="counter">
            {index + 1} / {items.length}
            {hasMore ? "+" : ""}
          </span>
          <span className="player-spacer" />
          {video && downloaded ? (
            <button type="button" className="icon-btn" aria-label={muted ? t("取消静音") : t("静音")} onClick={toggleMute}>
              {muted ? <SpeakerSlash size={20} /> : <SpeakerHigh size={20} />}
            </button>
          ) : null}
          <button
            type="button"
            className={`icon-btn${autoNext ? " is-active" : ""}`}
            aria-label={autoNext ? t("关闭自动连播") : t("开启自动连播")}
            aria-pressed={autoNext}
            title={autoNext ? t("自动连播：开") : t("自动连播：关（单个循环）")}
            onClick={() =>
              setAutoNext((value) => {
                writeFlag(AUTOPLAY_KEY, !value);
                return !value;
              })
            }
          >
            <Repeat size={20} />
          </button>
          <button type="button" className={`icon-btn${panelOpen ? " is-active" : ""}`} aria-label={t("作品详情")} aria-pressed={panelOpen} onClick={togglePanel}>
            <Info size={20} />
          </button>
        </div>

        <div className="player-nav">
          <button type="button" className={`icon-btn player-glass${item.starred ? " is-active" : ""}`} aria-label={item.starred ? t("取消精选") : t("加入精选")} aria-pressed={Boolean(item.starred)} onClick={() => void star()}>
            <Star size={22} weight={item.starred ? "fill" : "regular"} />
          </button>
          <button type="button" className="icon-btn player-glass is-desktop" aria-label={t("上一个")} disabled={atStart} onClick={() => go(-1)}>
            <CaretUp size={22} weight="bold" />
          </button>
          <button type="button" className="icon-btn player-glass is-desktop" aria-label={t("下一个")} disabled={atEnd} onClick={() => go(1)}>
            <CaretDown size={22} weight="bold" />
          </button>
        </div>

        {!panelOpen ? (
          <div className="player-caption">
            <button type="button" className="player-author" onClick={() => onOpenCreator?.(item.creatorId, name)}>
              <Avatar src={item.creator?.avatarUrl} name={name} />@{name}
            </button>
            {item.description ? <p>{item.description}</p> : null}
          </div>
        ) : null}
      </div>

      {panelOpen ? (
        <DetailPanel
          item={item}
          onStar={() => void star()}
          onCopyLink={() => void copyLink()}
          onDownloadNow={() => void downloadNow()}
          onOpenCreator={onOpenCreator}
          onSearch={onSearch}
          onOpenSource={onOpenSource}
          onClose={togglePanel}
          onRemoteChecked={(remote) => onItemPatch?.(item.awemeId, { remoteAvailability: remote })}
          onPatch={(patch) => onItemPatch?.(item.awemeId, patch)}
          onOpenAlbum={onOpenAlbum}
          onOpenTag={onOpenTag}
        />
      ) : null}
    </div>
  );
}

function DetailPanel({
  item,
  onStar,
  onCopyLink,
  onDownloadNow,
  onOpenCreator,
  onSearch,
  onOpenSource,
  onClose,
  onRemoteChecked,
  onPatch,
  onOpenAlbum,
  onOpenTag,
}: {
  item: FeedItem;
  onPatch: (patch: Partial<FeedItem>) => void;
  onOpenAlbum?: (albumId: number) => void;
  onOpenTag?: (tag: string) => void;
  onStar: () => void;
  onCopyLink: () => void;
  onDownloadNow: () => void;
  onOpenCreator?: (creatorId: string | null, name: string) => void;
  onSearch?: (term: string) => void;
  onOpenSource?: (sourceId: string) => void;
  onClose: () => void;
  onRemoteChecked: (remote: RemoteAvailability) => void;
}) {
  const [checking, setChecking] = useState(false);
  const name = item.creator?.nickname || item.author;
  const statistics = item.douyin?.statistics ?? {};
  const stats = [
    [t("播放"), statistics.playCount],
    [t("点赞"), statistics.diggCount],
    [t("评论"), statistics.commentCount],
    [t("收藏"), statistics.collectCount],
    [t("分享"), statistics.shareCount],
  ].filter((entry): entry is [string, number] => typeof entry[1] === "number" && entry[1] > 0);
  const primary = item.media[0];
  const technical = primary?.technical;
  const totalBytes = item.media.reduce((sum, media) => sum + (media.byteSize ?? 0), 0);
  const remote = item.remoteAvailability ?? { status: "unknown" as const, checkedAt: null, evidenceCode: null, lastAvailableAt: null };
  const remoteLabel = REMOTE_LABEL[remote.status];
  const downloaded = item.local.state === "downloaded";

  async function recheck() {
    setChecking(true);
    try {
      onRemoteChecked(await checkRemoteAvailability(item.awemeId));
    } catch {
      // Leave the previous verdict in place; the badge already says what we know.
    } finally {
      setChecking(false);
    }
  }

  return (
    <aside className="player-panel" aria-label={t("作品详情")}>
      <div className="player-panel-scroll">
        <div className="panel-top">
          <button type="button" className="panel-author" onClick={() => onOpenCreator?.(item.creatorId, name)}>
            <Avatar src={item.creator?.avatarUrl} name={name} />
            <span>
              <strong>{name}</strong>
              <small>{item.creator?.uniqueId ? t("抖音号 {id}", { id: item.creator.uniqueId }) : t("查看博主的全部作品")}</small>
            </span>
          </button>
          <button type="button" className="icon-btn icon-btn-sm" aria-label={t("收起详情")} onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        {item.description ? <p className="panel-desc">{item.description}</p> : null}
        {item.douyin?.hashtags.length ? (
          <div className="panel-tags">
            {item.douyin.hashtags.map((tag) => (
              <button key={tag} type="button" onClick={() => onSearch?.(tag)}>
                #{tag}
              </button>
            ))}
          </div>
        ) : null}

        <div className="panel-actions">
          <button type="button" className={`panel-action${item.starred ? " is-active" : ""}`} onClick={onStar}>
            <Star size={20} weight={item.starred ? "fill" : "regular"} />
            {item.starred ? t("已精选") : t("精选")}
          </button>
          <AddToAlbumButton item={item} onItemPatch={onPatch} />
          {downloaded && primary ? (
            <a className="panel-action" href={primary.url} download={primary.relativePath?.split("/").pop() ?? undefined}>
              <DownloadSimple size={20} />
              {t("下载原片")}
            </a>
          ) : (
            <button type="button" className="panel-action" onClick={onDownloadNow}>
              <CloudArrowDown size={20} />
              {t("存到 NAS")}
            </button>
          )}
          <a className="panel-action" href={douyinUrl(item)} target="_blank" rel="noreferrer">
            <ArrowSquareOut size={20} />
            {t("抖音打开")}
          </a>
          <button type="button" className="panel-action" onClick={onCopyLink}>
            <LinkSimple size={20} />
            {t("复制链接")}
          </button>
        </div>

        <section className="panel-section">
          <h3>{t("我的整理")}</h3>
          {item.albums?.length ? (
            <div className="panel-links organize-albums">
              {item.albums.map((album) => (
                <button key={album.id} type="button" onClick={() => onOpenAlbum?.(album.id)}>
                  {album.name}
                </button>
              ))}
            </div>
          ) : null}
          <TagEditor item={item} onChange={(tags) => onPatch({ tags })} />
          {item.tags?.length && onOpenTag ? (
            <div className="panel-links tag-links">
              {item.tags.map((tag) => (
                <button key={tag} type="button" onClick={() => onOpenTag(tag)}>
                  查看 #{tag}
                </button>
              ))}
            </div>
          ) : null}
          <NoteEditor item={item} onChange={(note) => onPatch({ note })} />
        </section>

        {stats.length ? (
          <section className="panel-section">
            <h3>{t("抖音数据")}</h3>
            <dl className="panel-stats">
              {stats.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{formatCount(value)}</dd>
                </div>
              ))}
            </dl>
          </section>
        ) : null}

        {item.collections.length ? (
          <section className="panel-section">
            <h3>{t("所在收藏夹")}</h3>
            <div className="panel-links">
              {item.collections.map((collection) => (
                <button key={collection.id} type="button" onClick={() => onOpenSource?.(`favorite_collection:${collection.id}`)}>
                  {collection.name}
                </button>
              ))}
            </div>
          </section>
        ) : null}

        <section className="panel-section">
          <h3>{t("抖音上的状态")}</h3>
          <div className="remote">
            <span className={`badge ${remoteLabel.tone}`}>{remoteLabel.text}</span>
            <button type="button" className="btn btn-ghost btn-sm remote-recheck" disabled={checking} onClick={() => void recheck()}>
              {checking ? <Spinner size={14} /> : <ArrowClockwise size={14} weight="bold" />}
              {checking ? t("检查中") : t("重新检查")}
            </button>
          </div>
        </section>

        <section className="panel-section">
          <h3>{t("档案信息")}</h3>
          <dl className="panel-rows">
            <div>
              <dt>{t("类型")}</dt>
              <dd>{item.type === "gallery" ? t("图集 · {n} 张", { n: Math.max(item.local.totalAssets, item.media.length) }) : t("视频")}</dd>
            </div>
            {formatDuration(itemDurationMs(item)) ? (
              <div>
                <dt>{t("时长")}</dt>
                <dd>{formatDuration(itemDurationMs(item))}</dd>
              </div>
            ) : null}
            <div>
              <dt>{t("本地状态")}</dt>
              <dd>{downloaded ? t("已保存 · {size}", { size: formatBytes(totalBytes) }) : item.local.state === "downloading" ? t("下载中") : item.local.state === "failed" ? t("下载失败") : t("未下载")}</dd>
            </div>
            {technical?.width && technical.height ? (
              <div>
                <dt>{t("分辨率")}</dt>
                <dd>
                  {technical.width} × {technical.height}
                  {technical.fps && primary?.type === "video" ? ` · ${Math.round(technical.fps)} fps` : ""}
                </dd>
              </div>
            ) : null}
            {technical?.codec ? (
              <div>
                <dt>{t("编码")}</dt>
                <dd>
                  {technical.codec}
                  {technical.bitRate ? ` · ${(technical.bitRate / 1_000_000).toFixed(1)} Mbps` : ""}
                </dd>
              </div>
            ) : null}
            <div>
              <dt>{t("发布时间")}</dt>
              <dd>{formatDate(item.publishedAt)}</dd>
            </div>
            <div>
              <dt>{t("收藏时间")}</dt>
              <dd>{formatDate(item.archivedAt)}</dd>
            </div>
            <div>
              <dt>{t("作品 ID")}</dt>
              <dd className="num">{item.awemeId}</dd>
            </div>
            {primary?.relativePath ? (
              <div>
                <dt>{t("文件")}</dt>
                <dd className="is-wrap">{primary.relativePath}</dd>
              </div>
            ) : null}
          </dl>
        </section>

        <div className="panel-hint" aria-label={t("快捷键")}>
          <span><span className="kbd">↑</span><span className="kbd">↓</span>{t("切换")}</span>
          <span><span className="kbd">←</span><span className="kbd">→</span>{t("翻图")}</span>
          <span><span className="kbd">{t("空格")}</span>{t("暂停")}</span>
          <span><span className="kbd">S</span>{t("精选")}</span>
          <span><span className="kbd">M</span>{t("静音")}</span>
          <span><span className="kbd">I</span>{t("详情")}</span>
          <span><span className="kbd">Esc</span>{t("关闭")}</span>
        </div>
      </div>
    </aside>
  );
}
