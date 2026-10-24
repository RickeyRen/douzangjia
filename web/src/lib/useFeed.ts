import { useCallback, useEffect, useRef, useState } from "react";

import { fetchFeed, feedQueryString, type FeedItem, type FeedQuery } from "../app/api";

export type FeedState = {
  items: FeedItem[];
  loading: boolean;
  loadingMore: boolean;
  error: boolean;
  hasMore: boolean;
  loadMore: () => Promise<void>;
  retry: () => void;
  updateItem: (awemeId: string, patch: Partial<FeedItem>) => void;
};

/**
 * Cursor pagination for /api/feed. A changed query resets the list; responses
 * for an older query are dropped so fast filter changes never mix pages.
 */
export function useFeed(query: FeedQuery | null): FeedState {
  const key = query ? feedQueryString(query) : null;
  const [items, setItems] = useState<FeedItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(query !== null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const generation = useRef(0);
  const busy = useRef(false);
  const queryRef = useRef(query);
  queryRef.current = query;

  useEffect(() => {
    const current = ++generation.current;
    busy.current = false;
    setItems([]);
    setCursor(null);
    setError(false);
    setLoadingMore(false);
    if (key === null || queryRef.current === null) {
      setLoading(false);
      return;
    }
    setLoading(true);
    fetchFeed(queryRef.current)
      .then((page) => {
        if (current !== generation.current) return;
        setItems(page.items);
        setCursor(page.nextCursor);
      })
      .catch(() => {
        if (current === generation.current) setError(true);
      })
      .finally(() => {
        if (current === generation.current) setLoading(false);
      });
  }, [key, attempt]);

  const loadMore = useCallback(async () => {
    const base = queryRef.current;
    if (!base || !cursor || busy.current) return;
    const current = generation.current;
    busy.current = true;
    setLoadingMore(true);
    try {
      const page = await fetchFeed({ ...base, cursor });
      if (current !== generation.current) return;
      setItems((existing) => {
        const known = new Set(existing.map((item) => item.awemeId));
        return [...existing, ...page.items.filter((item) => !known.has(item.awemeId))];
      });
      setCursor(page.nextCursor);
      setError(false);
    } catch {
      if (current === generation.current) setError(true);
    } finally {
      if (current === generation.current) {
        busy.current = false;
        setLoadingMore(false);
      }
    }
  }, [cursor]);

  const updateItem = useCallback((awemeId: string, patch: Partial<FeedItem>) => {
    setItems((existing) => existing.map((item) => (item.awemeId === awemeId ? { ...item, ...patch } : item)));
  }, []);

  const retry = useCallback(() => {
    if (items.length > 0) void loadMore();
    else setAttempt((value) => value + 1);
  }, [items.length, loadMore]);

  return { items, loading, loadingMore, error, hasMore: cursor !== null, loadMore, retry, updateItem };
}
