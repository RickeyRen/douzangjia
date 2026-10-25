import { expect, it } from "vitest";

import { parseRoute, routeHref, sameSection, type Route } from "./router";

it.each<Route>([
  { name: "home" },
  { name: "library", filters: {} },
  { name: "library", sourceId: "favorite_collection:7374", filters: { type: "gallery", sort: "random", downloaded: true } },
  { name: "starred", filters: { sort: "published" } },
  { name: "search", query: "旅行 vlog", filters: { type: "video" } },
  { name: "creators", query: "小鹿" },
  { name: "creator", creatorId: "MS4wLjAB/x", filters: {} },
  { name: "album", albumId: 7, filters: { sort: "album" } },
  { name: "tag", tag: "做饭 周末", filters: {} },
  { name: "gone", filters: { type: "video" } },
  { name: "activity" },
  { name: "settings" },
])("round-trips %o through the hash", (route) => {
  expect(parseRoute(routeHref(route))).toEqual(route);
});

it("ignores unknown filter values instead of passing them to the API", () => {
  expect(parseRoute("#/library?type=movie&sort=views&dl=0")).toEqual({ name: "library", filters: {} });
  expect(parseRoute("#/nowhere")).toEqual({ name: "home" });
  expect(parseRoute("#/album/abc")).toEqual({ name: "library", filters: {} });
});

it("keeps a section highlighted while its filters change", () => {
  const plain: Route = { name: "library", sourceId: "a", filters: {} };
  expect(sameSection(plain, { name: "library", sourceId: "a", filters: { type: "video" } })).toBe(true);
  expect(sameSection(plain, { name: "library", sourceId: "b", filters: {} })).toBe(false);
  expect(sameSection(plain, { name: "library", filters: {} })).toBe(false);
});
