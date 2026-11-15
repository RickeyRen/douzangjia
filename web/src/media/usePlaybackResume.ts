import { useCallback, useEffect, useRef, useState, type RefObject } from "react";

import { fetchPlayback, savePlayback } from "../app/api";

/** Same threshold as the server: shorter clips always start from the top. */
export const RESUME_MIN_MS = 120_000;
const SAVE_EVERY_MS = 15_000;
const CHIP_MS = 6_000;

/**
 * Long videos pick up where they were left, on any device: the position lives
 * on the NAS. Saves while playing, on pause, and when the video is left.
 */
export function usePlaybackResume(
  itemId: string,
  element: RefObject<HTMLVideoElement | null>,
  current: boolean,
  knownDurationMs: number | null | undefined,
) {
  const [resumedAt, setResumedAt] = useState<number | null>(null);
  const lastSaved = useRef(0);

  const save = useCallback(
    (ended = false, captured?: HTMLVideoElement) => {
      // On unmount React has already cleared the ref; the effect hands its own copy.
      const node = captured ?? element.current;
      if (!node || !Number.isFinite(node.duration) || node.duration * 1000 < RESUME_MIN_MS) return;
      lastSaved.current = Date.now();
      const durationMs = Math.round(node.duration * 1000);
      // keepalive lets the last save finish even when the page is being closed.
      void savePlayback(itemId, ended ? durationMs : Math.round(node.currentTime * 1000), durationMs).catch(() => undefined);
    },
    [element, itemId],
  );

  useEffect(() => {
    const node = element.current;
    if (!current || !node) return;
    let cancelled = false;
    if ((knownDurationMs ?? Number.POSITIVE_INFINITY) >= RESUME_MIN_MS) {
      fetchPlayback(itemId)
        .then(({ positionMs }) => {
          if (cancelled || !positionMs) return;
          const seek = () => {
            if (cancelled) return;
            node.currentTime = positionMs / 1000;
            setResumedAt(positionMs);
          };
          if (node.readyState >= 1) seek();
          else node.addEventListener("loadedmetadata", seek, { once: true });
        })
        .catch(() => undefined);
    }
    const onHide = () => {
      if (document.visibilityState === "hidden") save();
    };
    document.addEventListener("visibilitychange", onHide);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onHide);
      if (!node.ended) save(false, node);
      setResumedAt(null);
    };
  }, [current, element, itemId, knownDurationMs, save]);

  useEffect(() => {
    if (resumedAt === null) return;
    const timer = window.setTimeout(() => setResumedAt(null), CHIP_MS);
    return () => window.clearTimeout(timer);
  }, [resumedAt]);

  return {
    resumedAt,
    restart: () => {
      const node = element.current;
      if (node) node.currentTime = 0;
      setResumedAt(null);
    },
    onTimeUpdate: () => {
      if (current && Date.now() - lastSaved.current >= SAVE_EVERY_MS) save();
    },
    onPause: () => {
      if (current && !element.current?.ended) save();
    },
    onEnded: () => {
      if (current) save(true);
    },
  };
}
