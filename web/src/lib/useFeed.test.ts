import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import * as api from "../app/api";
import type { FeedQuery } from "../app/api";
import { makeItem } from "../test/fixtures";
import { useFeed } from "./useFeed";

vi.mock("../app/api", async (original) => ({ ...(await original<typeof api>()), fetchFeed: vi.fn() }));

beforeEach(() => vi.mocked(api.fetchFeed).mockReset());

it("appends pages without duplicates and stops at the last cursor", async () => {
  vi.mocked(api.fetchFeed)
    .mockResolvedValueOnce({ items: [makeItem({ awemeId: "701" }), makeItem({ awemeId: "702" })], nextCursor: "c1" })
    .mockResolvedValueOnce({ items: [makeItem({ awemeId: "702" }), makeItem({ awemeId: "703" })], nextCursor: null });
  const query: FeedQuery = { sort: "archived" };
  const { result } = renderHook(() => useFeed(query));
  await waitFor(() => expect(result.current.items).toHaveLength(2));
  expect(result.current.hasMore).toBe(true);

  await act(() => result.current.loadMore());

  expect(result.current.items.map((item) => item.awemeId)).toEqual(["701", "702", "703"]);
  expect(result.current.hasMore).toBe(false);
  expect(vi.mocked(api.fetchFeed).mock.calls[1][0]).toEqual({ sort: "archived", cursor: "c1" });
});

it("drops a slow response from a filter the user already left", async () => {
  let resolveOld: (value: api.Page<api.FeedItem>) => void = () => undefined;
  vi.mocked(api.fetchFeed)
    .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }))
    .mockResolvedValueOnce({ items: [makeItem({ awemeId: "900" })], nextCursor: null });
  const { result, rerender } = renderHook(({ query }) => useFeed(query), { initialProps: { query: { type: "video" } as FeedQuery } });

  rerender({ query: { type: "gallery" } });
  await waitFor(() => expect(result.current.items.map((item) => item.awemeId)).toEqual(["900"]));
  await act(async () => resolveOld({ items: [makeItem({ awemeId: "111" })], nextCursor: null }));

  expect(result.current.items.map((item) => item.awemeId)).toEqual(["900"]);
});

it("patches one item in place for optimistic stars", async () => {
  vi.mocked(api.fetchFeed).mockResolvedValueOnce({ items: [makeItem({ awemeId: "701" })], nextCursor: null });
  const { result } = renderHook(() => useFeed({}));
  await waitFor(() => expect(result.current.items).toHaveLength(1));

  act(() => result.current.updateItem("701", { starred: true }));

  expect(result.current.items[0].starred).toBe(true);
});
