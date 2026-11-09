import type { HomeActivity } from "../app/api";
import { t } from "../i18n/t";

export const DAY_SECONDS = 86_400;

/** Fills empty buckets with zero so a quiet hour reads as a dip rather than a straight line. */
export function speedSeries(points: HomeActivity["speed"], bucket: number, now: number) {
  const end = Math.floor(now / bucket) * bucket;
  const start = end - DAY_SECONDS + bucket;
  const byBucket = new Map(points.map((point) => [point.at, point.bps]));
  const series: Array<{ at: number; bps: number }> = [];
  for (let at = start; at <= end; at += bucket) series.push({ at, bps: byBucket.get(at) ?? 0 });
  return series;
}

export type HeatCell = { date: string; count: number; level: number; future: boolean } | null;

function parseDay(date: string): Date {
  const [year, month, day] = date.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

/** Seven rows (Mon–Sun) by ten week columns, the last column holding today. */
export function heatmapGrid(daily: HomeActivity["dailySaved"], weeks = 10) {
  const max = daily.reduce((best, day) => Math.max(best, day.count), 0);
  const level = (count: number) => (count <= 0 || max <= 0 ? 0 : Math.min(4, Math.ceil((count / max) * 4)));
  const byDate = new Map(daily.map((day) => [day.date, day.count]));
  const columns: Array<{ month: string | null; cells: HeatCell[] }> = [];
  if (!daily.length) return { columns, max };
  const today = parseDay(daily[daily.length - 1].date);
  const weekday = (today.getUTCDay() + 6) % 7;
  const firstMonday = new Date(today.getTime() - (weekday + (weeks - 1) * 7) * DAY_SECONDS * 1000);
  let lastMonth = -1;
  for (let week = 0; week < weeks; week += 1) {
    const cells: HeatCell[] = [];
    let month: string | null = null;
    for (let day = 0; day < 7; day += 1) {
      const date = new Date(firstMonday.getTime() + (week * 7 + day) * DAY_SECONDS * 1000);
      const iso = date.toISOString().slice(0, 10);
      if (day === 0 && date.getUTCMonth() !== lastMonth) {
        month = t("{m}月", { m: date.getUTCMonth() + 1 });
        lastMonth = date.getUTCMonth();
      }
      if (date > today) cells.push({ date: iso, count: 0, level: 0, future: true });
      else if (!byDate.has(iso)) cells.push(null);
      else {
        const count = byDate.get(iso) ?? 0;
        cells.push({ date: iso, count, level: level(count), future: false });
      }
    }
    columns.push({ month, cells });
  }
  return { columns, max };
}

/** Days in a row with at least one save, counting back from today (or yesterday if today is still empty). */
export function savingStreak(daily: HomeActivity["dailySaved"]): number {
  let index = daily.length - 1;
  if (index >= 0 && daily[index].count === 0) index -= 1;
  let streak = 0;
  while (index >= 0 && daily[index].count > 0) {
    streak += 1;
    index -= 1;
  }
  return streak;
}

