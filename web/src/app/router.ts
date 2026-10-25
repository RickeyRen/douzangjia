import { useSyncExternalStore } from "react";

import type { DurationBucket, FeedSort, PeriodBucket } from "./api";

export type LibraryFilters = {
  type?: "video" | "gallery";
  sort?: FeedSort;
  downloaded?: boolean;
  duration?: DurationBucket;
  period?: PeriodBucket;
};

export type Route =
  | { name: "home" }
  | { name: "library"; sourceId?: string; filters: LibraryFilters }
  | { name: "starred"; filters: LibraryFilters }
  | { name: "search"; query: string; filters: LibraryFilters }
  | { name: "creators"; query: string }
  | { name: "creator"; creatorId: string; filters: LibraryFilters }
  | { name: "album"; albumId: number; filters: LibraryFilters }
  | { name: "tag"; tag: string; filters: LibraryFilters }
  | { name: "gone"; filters: LibraryFilters }
  | { name: "activity" }
  | { name: "settings" };

const SORTS = new Set<FeedSort>(["archived", "published", "source", "starred", "random", "album", "relevance"]);
const DURATIONS = new Set<DurationBucket>(["short", "medium", "long"]);
const PERIODS = new Set<PeriodBucket>(["week", "month", "quarter", "year"]);

function readFilters(params: URLSearchParams): LibraryFilters {
  const type = params.get("type");
  const sort = params.get("sort") as FeedSort | null;
  const duration = params.get("dur") as DurationBucket | null;
  const period = params.get("in") as PeriodBucket | null;
  return {
    type: type === "video" || type === "gallery" ? type : undefined,
    sort: sort && SORTS.has(sort) ? sort : undefined,
    downloaded: params.get("dl") === "1" || undefined,
    duration: duration && DURATIONS.has(duration) ? duration : undefined,
    period: period && PERIODS.has(period) ? period : undefined,
  };
}

function writeFilters(params: URLSearchParams, filters: LibraryFilters) {
  if (filters.type) params.set("type", filters.type);
  if (filters.sort) params.set("sort", filters.sort);
  if (filters.downloaded) params.set("dl", "1");
  if (filters.duration) params.set("dur", filters.duration);
  if (filters.period) params.set("in", filters.period);
}

export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#/, "");
  const [pathPart, queryPart = ""] = raw.split("?", 2);
  const segments = pathPart.split("/").filter(Boolean).map(decodeURIComponent);
  const params = new URLSearchParams(queryPart);
  const filters = readFilters(params);
  switch (segments[0]) {
    case "library":
      return segments[1] ? { name: "library", sourceId: segments[1], filters } : { name: "library", filters };
    case "starred":
      return { name: "starred", filters };
    case "search":
      return { name: "search", query: params.get("q") ?? "", filters };
    case "creators":
      return { name: "creators", query: params.get("q") ?? "" };
    case "creator":
      return segments[1] ? { name: "creator", creatorId: segments[1], filters } : { name: "creators", query: "" };
    case "album": {
      const albumId = Number(segments[1]);
      return Number.isInteger(albumId) && albumId > 0 ? { name: "album", albumId, filters } : { name: "library", filters };
    }
    case "tag":
      return segments[1] ? { name: "tag", tag: segments[1], filters } : { name: "library", filters };
    case "gone":
      return { name: "gone", filters };
    case "activity":
      return { name: "activity" };
    case "settings":
      return { name: "settings" };
    default:
      return { name: "home" };
  }
}

export function routeHref(route: Route): string {
  const params = new URLSearchParams();
  let path = "/";
  switch (route.name) {
    case "home":
      break;
    case "library":
      path = route.sourceId ? `/library/${encodeURIComponent(route.sourceId)}` : "/library";
      writeFilters(params, route.filters);
      break;
    case "starred":
      path = "/starred";
      writeFilters(params, route.filters);
      break;
    case "search":
      path = "/search";
      if (route.query) params.set("q", route.query);
      writeFilters(params, route.filters);
      break;
    case "creators":
      path = "/creators";
      if (route.query) params.set("q", route.query);
      break;
    case "creator":
      path = `/creator/${encodeURIComponent(route.creatorId)}`;
      writeFilters(params, route.filters);
      break;
    case "album":
      path = `/album/${route.albumId}`;
      writeFilters(params, route.filters);
      break;
    case "tag":
      path = `/tag/${encodeURIComponent(route.tag)}`;
      writeFilters(params, route.filters);
      break;
    case "gone":
      path = "/gone";
      writeFilters(params, route.filters);
      break;
    case "activity":
      path = "/activity";
      break;
    case "settings":
      path = "/settings";
      break;
  }
  const query = params.toString();
  return `#${path}${query ? `?${query}` : ""}`;
}

export function navigate(route: Route, { replace = false }: { replace?: boolean } = {}) {
  const href = routeHref(route);
  if (window.location.hash === href) return;
  if (replace) {
    window.history.replaceState(null, "", href);
    window.dispatchEvent(new HashChangeEvent("hashchange"));
  } else {
    window.location.hash = href;
  }
}

function subscribe(callback: () => void) {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash, () => "");
  return parseRoute(hash);
}

/** Routes compare by href so navigation highlights survive filter changes. */
export function sameSection(a: Route, b: Route): boolean {
  if (a.name !== b.name) return false;
  if (a.name === "library" && b.name === "library") return a.sourceId === b.sourceId;
  if (a.name === "creator" && b.name === "creator") return a.creatorId === b.creatorId;
  if (a.name === "album" && b.name === "album") return a.albumId === b.albumId;
  if (a.name === "tag" && b.name === "tag") return a.tag === b.tag;
  return true;
}
