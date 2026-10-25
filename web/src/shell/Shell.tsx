import {
  ArrowClockwise,
  CaretDown,
  CaretUp,
  GearSix,
  House,
  Images,
  MagnifyingGlass,
  Plus,
  Moon,
  Pulse,
  QrCode,
  Shuffle,
  SquaresFour,
  Star,
  Sun,
  Users,
  Warning,
  X,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { createAlbum, triggerSync } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { navigate, routeHref, sameSection, useRoute, type Route } from "../app/router";
import { describeHealth } from "../lib/health";
import { useTheme } from "../theme/theme-context";
import { groupSources, sourceLabel } from "./sourceMeta";
import { SourceIcon } from "./SourceIcon";

export function Shell({ children }: { children: ReactNode }) {
  const route = useRoute();
  return (
    <div className="shell">
      <Sidebar route={route} />
      <div className="main">
        <TopBar route={route} />
        <main className="content" key={routeHref(route).split("?")[0]}>
          <HealthBanner />
          {children}
        </main>
      </div>
      <TabBar route={route} />
    </div>
  );
}

function NavLink({ to, current, icon, label, count }: { to: Route; current: Route; icon: ReactNode; label: string; count?: number }) {
  const active = sameSection(to, current);
  return (
    <a className="nav-item" href={routeHref(to)} aria-current={active ? "page" : undefined}>
      {icon}
      <span className="nav-text">{label}</span>
      {count ? <span className="nav-count">{count.toLocaleString("zh-CN")}</span> : null}
    </a>
  );
}

function Sidebar({ route }: { route: Route }) {
  const { sources, health, albums, refreshAlbums, toast } = useAppData();
  const [showEmpty, setShowEmpty] = useState(false);
  const [newAlbum, setNewAlbum] = useState<string | null>(null);

  async function submitAlbum(event: FormEvent) {
    event.preventDefault();
    const name = (newAlbum ?? "").trim();
    if (!name) return;
    try {
      const album = await createAlbum(name);
      setNewAlbum(null);
      await refreshAlbums();
      navigate({ name: "album", albumId: album.id, filters: {} });
    } catch {
      toast("创建相册失败，可能已有同名相册");
    }
  }
  const groups = groupSources(sources);
  const view = describeHealth(health);
  return (
    <aside className="sidebar">
      <a className="brand" href="#/">
        <span className="brand-mark">
          <BrandGlyph />
        </span>
        <strong>抖藏家</strong>
      </a>
      <nav className="sidebar-scroll" aria-label="主导航">
        <div className="nav-group">
          <NavLink to={{ name: "home" }} current={route} icon={<House size={18} />} label="首页" />
          <NavLink to={{ name: "library", filters: {} }} current={route} icon={<SquaresFour size={18} />} label="全部作品" />
          <NavLink to={{ name: "starred", filters: {} }} current={route} icon={<Star size={18} />} label="精选" />
          <NavLink to={{ name: "creators", query: "" }} current={route} icon={<Users size={18} />} label="博主" />
        </div>
        <div className="nav-group">
          <div className="nav-label">
            相册
            <button type="button" className="nav-label-action" aria-label="新建相册" onClick={() => setNewAlbum("")}>
              <Plus size={14} weight="bold" />
            </button>
          </div>
          {albums.map((album) => (
            <NavLink key={album.id} to={{ name: "album", albumId: album.id, filters: {} }} current={route} icon={<Images size={18} />} label={album.name} count={album.itemCount} />
          ))}
          {newAlbum !== null ? (
            <form className="nav-create" onSubmit={(event) => void submitAlbum(event)}>
              <input autoFocus aria-label="新相册名称" placeholder="相册名称，回车创建" maxLength={60} value={newAlbum} onChange={(event) => setNewAlbum(event.target.value)} onBlur={() => !newAlbum && setNewAlbum(null)} onKeyDown={(event) => event.key === "Escape" && setNewAlbum(null)} />
            </form>
          ) : albums.length === 0 ? (
            <button type="button" className="nav-item nav-item-hint" onClick={() => setNewAlbum("")}>
              <Plus size={18} />
              <span className="nav-text">把作品整理进相册</span>
            </button>
          ) : null}
        </div>
        {groups.collections.length ? (
          <div className="nav-group">
            <div className="nav-label">收藏夹</div>
            {groups.collections.map((source) => (
              <NavLink
                key={source.id}
                to={{ name: "library", sourceId: source.id, filters: {} }}
                current={route}
                icon={<SourceIcon source={source} />}
                label={sourceLabel(source)}
                count={source.discoveredCount}
              />
            ))}
          </div>
        ) : null}
        <div className="nav-group">
          <div className="nav-label">抖音账号</div>
          {groups.accountActive.map((source) => (
            <NavLink key={source.id} to={{ name: "library", sourceId: source.id, filters: {} }} current={route} icon={<SourceIcon source={source} />} label={source.name} count={source.discoveredCount} />
          ))}
          {showEmpty
            ? groups.accountEmpty.map((source) => (
                <NavLink key={source.id} to={{ name: "library", sourceId: source.id, filters: {} }} current={route} icon={<SourceIcon source={source} />} label={source.name} />
              ))
            : null}
          {groups.accountEmpty.length ? (
            <button type="button" className="nav-item" onClick={() => setShowEmpty((value) => !value)} aria-expanded={showEmpty}>
              {showEmpty ? <CaretUp size={18} /> : <CaretDown size={18} />}
              <span className="nav-text">{showEmpty ? "收起空来源" : `还有 ${groups.accountEmpty.length} 个空来源`}</span>
            </button>
          ) : null}
        </div>
      </nav>
      <div className="sidebar-footer">
        <a className={`status-pill is-${view.tone}`} href={routeHref({ name: "activity" })} aria-current={route.name === "activity" ? "page" : undefined}>
          <span className="dot" />
          <span>
            <strong>{view.label}</strong>
            <small>同步与下载</small>
          </span>
        </a>
        <NavLink to={{ name: "settings" }} current={route} icon={<GearSix size={18} />} label="设置" />
      </div>
    </aside>
  );
}

export function BrandGlyph({ size = 17 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M6 4.5h8.2a3.8 3.8 0 0 1 3.8 3.8v11.2l-6-3.6-6 3.6V4.5Z" fill="currentColor" />
      <path d="M10 8.6v5l4-2.5-4-2.5Z" fill="var(--accent)" />
    </svg>
  );
}

function TopBar({ route }: { route: Route }) {
  const { theme, toggleTheme } = useTheme();
  const initial = route.name === "search" ? route.query : "";
  const [query, setQuery] = useState(initial);
  const [scrolled, setScrolled] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => setQuery(initial), [initial]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (event.key === "/" && target && !["INPUT", "TEXTAREA"].includes(target.tagName) && !document.querySelector(".player")) {
        event.preventDefault();
        input.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = query.trim();
    if (!value) return;
    navigate({ name: "search", query: value, filters: route.name === "search" ? route.filters : {} });
    input.current?.blur();
  }

  return (
    <header className={`topbar${scrolled ? " is-scrolled" : ""}`}>
      <a className="topbar-brand brand-mark" href="#/" aria-label="抖藏家首页">
        <BrandGlyph />
      </a>
      <form className="search" role="search" onSubmit={submit}>
        <MagnifyingGlass size={17} weight="bold" />
        <input
          ref={input}
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索作品描述、博主或抖音号"
          aria-label="搜索资料库"
          enterKeyHint="search"
        />
        {query ? (
          <button type="button" className="icon-btn icon-btn-sm search-clear" aria-label="清空搜索" onClick={() => setQuery("")}>
            <X size={14} weight="bold" />
          </button>
        ) : (
          <span className="kbd" aria-hidden="true">
            /
          </span>
        )}
      </form>
      <div className="topbar-actions">
        <a className="icon-btn" href={routeHref({ name: "library", filters: { sort: "random" } })} aria-label="随机浏览" title="随机浏览">
          <Shuffle size={19} />
        </a>
        <button type="button" className="icon-btn" aria-label={theme === "dark" ? "切换到浅色" : "切换到深色"} title="切换主题" onClick={toggleTheme}>
          {theme === "dark" ? <Sun size={19} /> : <Moon size={19} />}
        </button>
      </div>
    </header>
  );
}

function TabBar({ route }: { route: Route }) {
  const { health } = useAppData();
  const alert = describeHealth(health).alert;
  const tabs: Array<{ to: Route; label: string; icon: ReactNode; match: (route: Route) => boolean }> = [
    { to: { name: "home" }, label: "首页", icon: <House size={22} />, match: (r) => r.name === "home" },
    { to: { name: "library", filters: {} }, label: "资料库", icon: <SquaresFour size={22} />, match: (r) => r.name === "library" || r.name === "search" },
    { to: { name: "starred", filters: {} }, label: "精选", icon: <Star size={22} />, match: (r) => r.name === "starred" },
    { to: { name: "creators", query: "" }, label: "博主", icon: <Users size={22} />, match: (r) => r.name === "creators" || r.name === "creator" },
    { to: { name: "activity" }, label: "状态", icon: <Pulse size={22} />, match: (r) => r.name === "activity" || r.name === "settings" },
  ];
  return (
    <nav className="tabbar" aria-label="底部导航">
      {tabs.map((tab) => (
        <a key={tab.label} href={routeHref(tab.to)} aria-current={tab.match(route) ? "page" : undefined}>
          {tab.icon}
          {tab.label}
          {tab.label === "状态" && alert ? <span className="tab-alert" aria-label="同步异常" /> : null}
        </a>
      ))}
    </nav>
  );
}

export function HealthBanner() {
  const { health, refreshHealth, requestDouyinLogin, toast } = useAppData();
  const route = useRoute();
  const [busy, setBusy] = useState(false);
  const view = describeHealth(health);
  if (!view.alert || route.name === "activity") return null;

  async function syncNow() {
    setBusy(true);
    try {
      await triggerSync(false);
      toast("已开始同步");
      window.setTimeout(() => void refreshHealth(), 3000);
    } catch {
      toast("无法开始同步，请查看状态页");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`banner${view.tone === "danger" ? " is-danger" : ""}`} role="alert">
      <span className="banner-icon">
        <Warning size={19} weight="fill" />
      </span>
      <div className="banner-text">
        <strong>{view.title}</strong>
        <p>{view.body}</p>
      </div>
      <div className="banner-actions">
        {view.action === "login" ? (
          <button type="button" className="btn btn-primary btn-sm" onClick={requestDouyinLogin}>
            <QrCode size={16} weight="bold" />
            重新扫码
          </button>
        ) : view.action === "sync" ? (
          <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => void syncNow()}>
            <ArrowClockwise size={16} weight="bold" className={busy ? "spinner" : undefined} />
            立即同步
          </button>
        ) : null}
        <a className="btn btn-secondary btn-sm" href={routeHref({ name: "activity" })}>
          查看详情
        </a>
      </div>
    </div>
  );
}

