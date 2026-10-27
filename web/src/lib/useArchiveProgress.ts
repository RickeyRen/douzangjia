import { useSyncExternalStore } from "react";

import { fetchArchiveProgress, type ArchiveProgress } from "../app/api";

const ACTIVE_INTERVAL_MS = 3000;
const IDLE_INTERVAL_MS = 15_000;

/**
 * One poller shared by the home banner, the activity page and the sidebar, so
 * every place that shows download progress agrees and the NAS sees one request.
 */
let snapshot: ArchiveProgress | null = null;
let timer: number | null = null;
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) listener();
}

function schedule() {
  if (timer !== null) window.clearTimeout(timer);
  timer = null;
  if (listeners.size === 0) return;
  timer = window.setTimeout(() => void refreshArchiveProgress(), snapshot?.active ? ACTIVE_INTERVAL_MS : IDLE_INTERVAL_MS);
}

export function refreshArchiveProgress(): Promise<void> {
  if (inflight) return inflight;
  inflight = fetchArchiveProgress()
    .then((next) => {
      snapshot = next;
      emit();
    })
    .catch(() => undefined)
    .finally(() => {
      inflight = null;
      schedule();
    });
  return inflight;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (listeners.size === 1) void refreshArchiveProgress();
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== null) {
      window.clearTimeout(timer);
      timer = null;
    }
  };
}

/** `undefined` until the first answer arrives, so callers can tell loading from idle. */
export function useArchiveProgress(): ArchiveProgress | undefined {
  return useSyncExternalStore(subscribe, () => snapshot ?? undefined);
}

/** For tests. */
export function resetArchiveProgress() {
  snapshot = null;
  inflight = null;
  if (timer !== null) window.clearTimeout(timer);
  timer = null;
  listeners.clear();
}
