import {
  ArrowClockwise,
  Bell,
  CloudArrowDown,
  GearSix,
  Ghost,
  House,
  Keyboard,
  MagnifyingGlass,
  Moon,
  QrCode,
  Shuffle,
  SquaresFour,
  Sun,
  Users,
  Warning,
  X,
} from "@phosphor-icons/react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import { triggerSync } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { navigate, routeHref, useRoute, type Route } from "../app/router";
import { describeHealth } from "../lib/health";
import { useArchiveProgress } from "../lib/useArchiveProgress";
import { useTheme } from "../theme/theme-context";
import { CommandPalette } from "./CommandPalette";
import { ShortcutsHelp } from "./ShortcutsHelp";
import { t } from "../i18n/t";

type Overlay = "palette" | "help" | null;

export function Shell({ children }: { children: ReactNode }) {
  const route = useRoute();
  const [overlay, setOverlay] = useState<Overlay>(null);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = Boolean(target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOverlay((current) => (current === "palette" ? null : "palette"));
      } else if (event.key === "?" && !typing && !document.querySelector(".player")) {
        event.preventDefault();
        setOverlay((current) => (current === "help" ? null : "help"));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="shell">
      <TopBar route={route} onOverlay={setOverlay} />
      <main className="content page-enter" key={routeHref(route).split("?")[0]}>
        <HealthBanner />
        {children}
      </main>
      <TabBar route={route} />
      {overlay === "palette" ? <CommandPalette onClose={() => setOverlay(null)} /> : null}
      {overlay === "help" ? <ShortcutsHelp onClose={() => setOverlay(null)} /> : null}
    </div>
  );
}

type Section = "home" | "works" | "creators" | "vanished" | "downloads" | "settings";

/** Which top-level section a route belongs to, so the pill nav highlights the right tab. */
function sectionOf(route: Route): Section {
  switch (route.name) {
    case "home":
      return "home";
    case "creators":
    case "creator":
      return "creators";
    case "vanished":
      return "vanished";
    case "activity":
      return "downloads";
    case "settings":
      return "settings";
    default:
      return "works";
  }
}

const SECTIONS: Array<{ id: Section; to: Route; label: string; icon: (size: number) => ReactNode }> = [
  { id: "home", to: { name: "home" }, label: t("首页"), icon: (size) => <House size={size} /> },
  { id: "works", to: { name: "library", filters: {} }, label: t("作品"), icon: (size) => <SquaresFour size={size} /> },
  { id: "creators", to: { name: "creators", query: "" }, label: t("博主"), icon: (size) => <Users size={size} /> },
  { id: "vanished", to: { name: "vanished" }, label: t("消失的博主"), icon: (size) => <Ghost size={size} /> },
  { id: "downloads", to: { name: "activity" }, label: t("下载"), icon: (size) => <CloudArrowDown size={size} /> },
  { id: "settings", to: { name: "settings" }, label: t("设置"), icon: (size) => <GearSix size={size} /> },
];

/** Near-black tile with the coral bookmark; the brand mark keeps its own colors in every theme. */
export function AppIcon({ size = 32 }: { size?: number }) {
  return (
    <svg className="app-icon" width={size} height={size} viewBox="0 0 1024 1024" aria-hidden="true">
      <defs>
        <linearGradient id="app-icon-bg" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="1024">
          <stop offset="0" stopColor="#1C1C21" />
          <stop offset="1" stopColor="#0A0A0C" />
        </linearGradient>
        <linearGradient id="app-icon-mark" gradientUnits="userSpaceOnUse" x1="300" y1="250" x2="724" y2="790">
          <stop offset="0" stopColor="#FF5470" />
          <stop offset="1" stopColor="#EE1248" />
        </linearGradient>
      </defs>
      <rect width="1024" height="1024" rx="230" fill="url(#app-icon-bg)" />
      <path fill="url(#app-icon-mark)" stroke="url(#app-icon-mark)" strokeWidth="28" strokeLinejoin="round" d="M 356 264 H 668 Q 698 264 698 294 V 768 L 512 652 L 326 768 V 294 Q 326 264 356 264 Z" />
      <path fill="#121215" stroke="#121215" strokeWidth="30" strokeLinejoin="round" d="M 478 396 L 478 532 L 588 464 Z" />
    </svg>
  );
}

function TopBar({ route, onOverlay }: { route: Route; onOverlay: (overlay: Overlay) => void }) {
  const { health } = useAppData();
  const [scrolled, setScrolled] = useState(false);
  const progress = useArchiveProgress();
  const downloading = progress?.active;
  const downloadPercent = downloading && downloading.totalItems ? Math.floor((downloading.completedItems / downloading.totalItems) * 100) : null;
  const view = describeHealth(health);
  const current = sectionOf(route);
  const alerts = (view.alert ? 1 : 0) + (progress?.failedTotal ? 1 : 0);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const tone = downloading && view.tone === "ok" ? "busy" : view.tone;
  const nasLabel = view.tone === "danger" || view.tone === "warning" ? view.label : t("NAS 在线");
  const nasDetail = downloading
    ? downloading.status === "paused"
      ? t("下载已暂停")
      : t("正在存 {p}%", { p: downloadPercent ?? 0 })
    : view.tone === "danger" || view.tone === "warning"
      ? t("查看")
      : view.label;

  return (
    <header className={`topbar${scrolled ? " is-scrolled" : ""}`}>
      <a className="topbar-brand" href="#/" aria-label={t("抖藏家首页")}>
        <AppIcon size={32} />
        <strong>{t("抖藏家")}</strong>
        <span className="topbar-ver">{t("存档")}</span>
      </a>
      <nav className="topnav" aria-label={t("主导航")}>
        {SECTIONS.map((section) => (
          <a key={section.id} href={routeHref(section.to)} aria-current={current === section.id ? "page" : undefined}>
            {section.icon(15)}
            <span>{section.label}</span>
            {section.id === "downloads" && downloadPercent !== null ? <em className="topnav-badge num">{downloadPercent}%</em> : null}
          </a>
        ))}
      </nav>
      <div className="topbar-actions">
        <a className={`nas-pill is-${tone}`} href={routeHref({ name: "activity" })} title={view.title}>
          <span className="dot" />
          <span className="nas-pill-label">{nasLabel}</span>
          <em>{nasDetail}</em>
        </a>
        <SearchButton route={route} />
        <a className="round-btn" href={routeHref({ name: "activity" })} aria-label={alerts ? t("有 {n} 条需要处理的提醒", { n: alerts }) : t("提醒")} title={t("同步与下载提醒")}>
          <Bell size={17} />
          {alerts ? <i className="round-btn-badge" /> : null}
        </a>
        <AccountMenu onOverlay={onOverlay} />
      </div>
    </header>
  );
}

function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onDown(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return { open, setOpen, ref };
}

function SearchButton({ route }: { route: Route }) {
  const initial = route.name === "search" ? route.query : "";
  const [query, setQuery] = useState(initial);
  const { open, setOpen, ref } = usePopover();

  useEffect(() => setQuery(initial), [initial]);
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (event.key === "/" && target && !["INPUT", "TEXTAREA"].includes(target.tagName) && !document.querySelector(".player")) {
        event.preventDefault();
        setOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const value = query.trim();
    if (!value) return;
    navigate({ name: "search", query: value, filters: route.name === "search" ? route.filters : {} });
    setOpen(false);
  }

  return (
    <div className="top-pop" ref={ref}>
      <button type="button" className={`round-btn${open || initial ? " is-on" : ""}`} aria-label={t("搜索资料库")} aria-expanded={open} title={t("搜索（/）")} onClick={() => setOpen(!open)}>
        <MagnifyingGlass size={17} />
      </button>
      {open ? (
        <form className="search search-pop" role="search" onSubmit={submit}>
          <MagnifyingGlass size={17} weight="bold" />
          <input
            autoFocus
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("搜索作品描述、博主或抖音号")}
            aria-label={t("搜索关键词")}
            enterKeyHint="search"
          />
          {query ? (
            <button type="button" className="icon-btn icon-btn-sm search-clear" aria-label={t("清空搜索")} onClick={() => setQuery("")}>
              <X size={14} weight="bold" />
            </button>
          ) : null}
        </form>
      ) : null}
    </div>
  );
}

function AccountMenu({ onOverlay }: { onOverlay: (overlay: Overlay) => void }) {
  const { account } = useAppData();
  const { theme, toggleTheme } = useTheme();
  const { open, setOpen, ref } = usePopover();
  const [avatarFailed, setAvatarFailed] = useState(false);
  const nickname = account?.account?.nickname ?? "";
  const avatar = account?.account?.avatarUrl;
  const initial = nickname.trim().slice(0, 1) || t("我");

  return (
    <div className="top-pop" ref={ref}>
      <button type="button" className="me-btn" aria-label={t("账号与外观")} aria-expanded={open} onClick={() => setOpen(!open)}>
        {avatar && !avatarFailed ? <img src={avatar} alt="" referrerPolicy="no-referrer" onError={() => setAvatarFailed(true)} /> : initial}
      </button>
      {open ? (
        <div className="menu-pop" role="menu">
          {nickname ? (
            <div className="menu-pop-head">
              <strong>{nickname}</strong>
              <small>{t("抖音账号已连接")}</small>
            </div>
          ) : null}
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              toggleTheme();
              setOpen(false);
            }}
          >
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
            {theme === "dark" ? t("切换到浅色") : t("切换到深色")}
          </button>
          <a role="menuitem" href={routeHref({ name: "library", filters: { sort: "random" } })} onClick={() => setOpen(false)}>
            <Shuffle size={17} />
            {t("随机浏览")}
          </a>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onOverlay("palette");
              setOpen(false);
            }}
          >
            <MagnifyingGlass size={17} />
            {t("命令面板")}
            <span className="kbd">⌘K</span>
          </button>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              onOverlay("help");
              setOpen(false);
            }}
          >
            <Keyboard size={17} />
            {t("快捷键")}
            <span className="kbd">?</span>
          </button>
          <a role="menuitem" href={routeHref({ name: "settings" })} onClick={() => setOpen(false)}>
            <GearSix size={17} />
            {t("设置")}
          </a>
        </div>
      ) : null}
    </div>
  );
}

function TabBar({ route }: { route: Route }) {
  const { health } = useAppData();
  const alert = describeHealth(health).alert;
  const current = sectionOf(route);
  const tabs = SECTIONS.filter((section) => section.id !== "vanished");
  return (
    <nav className="tabbar" aria-label={t("底部导航")}>
      {tabs.map((tab) => {
        const active = current === tab.id || (tab.id === "creators" && current === "vanished");
        return (
          <a key={tab.id} href={routeHref(tab.to)} aria-current={active ? "page" : undefined}>
            {tab.icon(22)}
            {tab.label}
            {tab.id === "downloads" && alert ? <span className="tab-alert" aria-label={t("同步异常")} /> : null}
          </a>
        );
      })}
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
      toast(t("已开始同步"));
      window.setTimeout(() => void refreshHealth(), 3000);
    } catch {
      toast(t("无法开始同步，请查看状态页"));
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
            {t("重新扫码")}
          </button>
        ) : view.action === "sync" ? (
          <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => void syncNow()}>
            <ArrowClockwise size={16} weight="bold" className={busy ? "spinner" : undefined} />
            {t("立即同步")}
          </button>
        ) : null}
        <a className="btn btn-secondary btn-sm" href={routeHref({ name: "activity" })}>
          {t("查看详情")}
        </a>
      </div>
    </div>
  );
}
