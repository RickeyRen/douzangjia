import { useEffect, useRef, useState } from "react";

import {
  fetchDashboard,
  fetchDashboardSeries,
  type DashboardSnapshot,
  type MetricPoint,
} from "../app/api";

export type DashboardStreamState = {
  snapshot: DashboardSnapshot | null;
  series: MetricPoint[];
  connected: boolean;
  loading: boolean;
  error: boolean;
};

export function useDashboardStream(enabled = true): DashboardStreamState {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | null>(null);
  const [series, setSeries] = useState<MetricPoint[]>([]);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(enabled);
  const [error, setError] = useState(false);
  const lastSeriesRefreshAt = useRef(0);

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      return;
    }
    let active = true;
    const eventSource = new EventSource("/api/events");
    void Promise.all([fetchDashboard(), fetchDashboardSeries("24h")])
      .then(([nextSnapshot, nextSeries]) => {
        if (!active) return;
        setSnapshot(nextSnapshot);
        setSeries(nextSeries.items);
        lastSeriesRefreshAt.current = nextSnapshot.generatedAt;
        setError(false);
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    const onSnapshot = (event: MessageEvent<string>) => {
      try {
        const next = JSON.parse(event.data) as DashboardSnapshot;
        if (!active) return;
        setSnapshot(next);
        setConnected(true);
        setError(false);
        if (next.generatedAt - lastSeriesRefreshAt.current >= 5) {
          lastSeriesRefreshAt.current = next.generatedAt;
          void fetchDashboardSeries("24h").then((nextSeries) => {
            if (active) setSeries(nextSeries.items);
          }).catch(() => {
            // Keep the last persisted series visible while the next sample retries.
          });
        }
      } catch {
        if (active) setError(true);
      }
    };
    eventSource.addEventListener("snapshot", onSnapshot as EventListener);
    eventSource.onopen = () => {
      if (active) setConnected(true);
    };
    eventSource.onerror = () => {
      if (active) setConnected(false);
    };

    return () => {
      active = false;
      eventSource.removeEventListener("snapshot", onSnapshot as EventListener);
      eventSource.close();
    };
  }, [enabled]);

  return { snapshot, series, connected, loading, error };
}
