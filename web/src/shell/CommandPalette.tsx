import { CloudSlash, GearSix, House, Images, MagnifyingGlass, Pulse, SquaresFour, Star, User, Users } from "@phosphor-icons/react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { fetchCreators, type Creator } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { navigate, type Route } from "../app/router";
import { SourceIcon } from "./SourceIcon";
import { groupSources, sourceLabel } from "./sourceMeta";

type Entry = { id: string; label: string; hint?: string; icon: ReactNode; route: Route };

const PAGES: Entry[] = [
  { id: "home", label: "首页", icon: <House size={16} />, route: { name: "home" } },
  { id: "library", label: "全部作品", icon: <SquaresFour size={16} />, route: { name: "library", filters: {} } },
  { id: "starred", label: "精选", icon: <Star size={16} />, route: { name: "starred", filters: {} } },
  { id: "creators", label: "博主", icon: <Users size={16} />, route: { name: "creators", query: "" } },
  { id: "gone", label: "已在抖音消失", icon: <CloudSlash size={16} />, route: { name: "gone", filters: {} } },
  { id: "activity", label: "同步与下载", icon: <Pulse size={16} />, route: { name: "activity" } },
  { id: "settings", label: "设置", icon: <GearSix size={16} />, route: { name: "settings" } },
];

function matches(label: string, query: string): boolean {
  return label.toLowerCase().includes(query.toLowerCase());
}

export function CommandPalette({ onClose }: { onClose: () => void }) {
  const { sources, albums } = useAppData();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [creators, setCreators] = useState<Creator[]>([]);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => input.current?.focus(), []);

  useEffect(() => {
    const term = query.trim();
    if (!term) {
      setCreators([]);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      fetchCreators({ search: term, sort: "items" })
        .then((page) => active && setCreators(page.items.slice(0, 6)))
        .catch(() => active && setCreators([]));
    }, 180);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  const entries = useMemo<Entry[]>(() => {
    const term = query.trim();
    const groups = groupSources(sources);
    const sourceEntries: Entry[] = [...groups.collections, ...groups.accountActive].map((source) => ({
      id: `source:${source.id}`,
      label: sourceLabel(source),
      hint: `${source.discoveredCount} 个作品`,
      icon: <SourceIcon source={source} size={16} />,
      route: { name: "library", sourceId: source.id, filters: {} },
    }));
    const albumEntries: Entry[] = albums.map((album) => ({
      id: `album:${album.id}`,
      label: album.name,
      hint: `相册 · ${album.itemCount}`,
      icon: <Images size={16} />,
      route: { name: "album", albumId: album.id, filters: {} },
    }));
    const creatorEntries: Entry[] = creators.map((creator) => ({
      id: `creator:${creator.id}`,
      label: creator.nickname,
      hint: creator.uniqueId ? `博主 · ${creator.uniqueId}` : "博主",
      icon: <User size={16} />,
      route: { name: "creator", creatorId: creator.id, filters: {} },
    }));
    const all = [...PAGES, ...albumEntries, ...sourceEntries];
    const filtered = term ? all.filter((entry) => matches(entry.label, term)) : all;
    const search: Entry[] = term
      ? [{ id: "search", label: `搜索“${term}”`, hint: "作品描述、话题、标签、备注", icon: <MagnifyingGlass size={16} />, route: { name: "search", query: term, filters: {} } }]
      : [];
    return [...filtered, ...creatorEntries, ...search];
  }, [albums, creators, query, sources]);

  useEffect(() => setActive(0), [query, entries.length]);

  function choose(entry: Entry | undefined) {
    if (!entry) return;
    onClose();
    navigate(entry.route);
  }

  function onKey(event: React.KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((value) => Math.min(entries.length - 1, value + 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((value) => Math.max(0, value - 1));
    } else if (event.key === "Enter") {
      event.preventDefault();
      choose(entries[active]);
    } else if (event.key === "Escape") {
      onClose();
    }
  }

  useEffect(() => {
    list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView?.({ block: "nearest" });
  }, [active]);

  return (
    <div className="scrim scrim-top" onClick={onClose}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="命令面板" onClick={(event) => event.stopPropagation()}>
        <div className="palette-input">
          <MagnifyingGlass size={18} weight="bold" />
          <input ref={input} aria-label="跳转或搜索" placeholder="跳到收藏夹、相册、博主，或搜索作品…" value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={onKey} />
          <span className="kbd">Esc</span>
        </div>
        <div ref={list} className="palette-list" role="listbox" aria-label="结果">
          {entries.length === 0 ? <p className="empty-note">没有匹配的内容</p> : null}
          {entries.map((entry, index) => (
            <button key={entry.id} type="button" role="option" aria-selected={index === active} data-index={index} className={`palette-item${index === active ? " is-active" : ""}`} onMouseEnter={() => setActive(index)} onClick={() => choose(entry)}>
              <span className="palette-icon">{entry.icon}</span>
              <span className="palette-label">{entry.label}</span>
              {entry.hint ? <small>{entry.hint}</small> : null}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
