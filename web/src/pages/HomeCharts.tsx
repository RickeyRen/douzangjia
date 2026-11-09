import { ArrowUpRight } from "@phosphor-icons/react";
import { useState } from "react";

import type { HomeActivity } from "../app/api";
import { routeHref } from "../app/router";
import { formatInteger, formatSpeed } from "../lib/format";
import { t } from "../i18n/t";
import { heatmapGrid, savingStreak, speedSeries } from "./homeChartData";

const WEEKDAYS = [t("周一"), t("周二"), t("周三"), t("周四"), t("周五"), t("周六"), t("周日")];

function clock(unixSeconds: number): string {
  const date = new Date(unixSeconds * 1000);
  return `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}`;
}

export function SpeedChart({ activity, currentBps }: { activity: HomeActivity | undefined; currentBps: number | null }) {
  const bucket = activity?.speedBucketSeconds || 600;
  const points = activity?.speed ?? [];
  const [now] = useState(() => Date.now() / 1000);
  const series = speedSeries(points, bucket, now);
  const sampled = points.filter((point) => point.bps > 0);
  const average = sampled.length ? sampled.reduce((sum, point) => sum + point.bps, 0) / sampled.length : 0;
  const peak = series.reduce((best, point) => (point.bps > best.bps ? point : best), series[0] ?? { at: 0, bps: 0 });
  const latest = points.length ? points[points.length - 1].bps : 0;
  const shown = currentBps ?? latest;
  const max = Math.max(peak.bps, 1) * 1.18;
  const width = 800;
  const height = 200;
  const x = (index: number) => (series.length > 1 ? (index / (series.length - 1)) * width : 0);
  const y = (bps: number) => height - (bps / max) * height;
  const line = series.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point.bps).toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const peakIndex = series.indexOf(peak);
  const [shownValue, shownUnit] = formatSpeed(shown).split(" ");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => series[Math.min(series.length - 1, Math.round(fraction * (series.length - 1)))]);

  return (
    <section className="card ch" aria-label={t("下载速度")}>
      <div className="row-h top">
        <div>
          <h2 className="h4">{t("下载速度")}</h2>
          <p className="cap">
            {sampled.length
              ? t("最近 24 小时 · 每 {m} 分钟取平均 · 虚线为平均 {avg}", { m: Math.round(bucket / 60), avg: formatSpeed(average) })
              : t("最近 24 小时 · 每 {m} 分钟取平均", { m: Math.round(bucket / 60) })}
          </p>
        </div>
        <span className="sp" />
        <a className="circ" href={routeHref({ name: "activity" })} aria-label={t("查看下载详情")}>
          <ArrowUpRight size={14} />
        </a>
      </div>
      <div className="ch-n">
        <span className="num big">{shownValue}</span>
        <span className="kpi-u">{shownUnit}</span>
        {sampled.length ? <span className="pill olive">{t("峰值 {v}", { v: formatSpeed(peak.bps) })}</span> : null}
        <span className="cap2">{currentBps !== null ? t("当前速度") : sampled.length ? t("最近一次采样") : t("现在没有在下载")}</span>
      </div>
      {sampled.length ? (
        <div className="ch-wrap">
          <div className="ch-plot">
            <svg className="chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={t("最近 24 小时下载速度曲线")}>
              <defs>
                <linearGradient id="speed-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0" stopColor="var(--accent-2)" stopOpacity="0.55" />
                  <stop offset="1" stopColor="var(--accent)" stopOpacity="0.02" />
                </linearGradient>
                <pattern id="speed-dots" width="6" height="6" patternUnits="userSpaceOnUse">
                  <circle cx="1" cy="1" r="0.8" fill="var(--accent-2)" opacity="0.35" />
                </pattern>
              </defs>
              {[0.25, 0.5, 0.75].map((fraction) => (
                <line key={fraction} className="ch-grid" x1="0" x2={width} y1={height * fraction} y2={height * fraction} vectorEffect="non-scaling-stroke" />
              ))}
              <path d={area} fill="url(#speed-fill)" />
              <path d={area} fill="url(#speed-dots)" />
              <line className="ch-avg" x1="0" x2={width} y1={y(average)} y2={y(average)} vectorEffect="non-scaling-stroke" />
              <path d={line} className="ch-line" vectorEffect="non-scaling-stroke" />
              <line className="ch-peak" x1={x(peakIndex)} x2={x(peakIndex)} y1={y(peak.bps)} y2={height} vectorEffect="non-scaling-stroke" />
            </svg>
            <span className="ch-dot" style={{ left: `${(x(peakIndex) / width) * 100}%`, top: `${(y(peak.bps) / height) * 100}%` }} />
            <span className="ch-dot is-end" style={{ left: "100%", top: `${(y(series[series.length - 1].bps) / height) * 100}%` }} />
            <div className={`tip${peakIndex / series.length > 0.8 ? " is-left" : peakIndex / series.length < 0.15 ? " is-right" : ""}`} style={{ left: `${(x(peakIndex) / width) * 100}%`, top: `${(y(peak.bps) / height) * 100}%` }}>
              <b className="num">{formatSpeed(peak.bps)}</b>
              <span>{t("{time} 峰值", { time: clock(peak.at) })}</span>
            </div>
          </div>
          <div className="ch-x num" aria-hidden="true">
            {ticks.map((tick, index) => (
              <span key={index}>{tick ? clock(tick.at) : ""}</span>
            ))}
          </div>
        </div>
      ) : (
        <div className="ch-empty">{t("最近 24 小时还没有下载记录。开始存到 NAS 后，这里会画出速度曲线。")}</div>
      )}
    </section>
  );
}

export function SavedHeatmap({ activity }: { activity: HomeActivity | undefined }) {
  const daily = activity?.dailySaved ?? [];
  const { columns, max } = heatmapGrid(daily);
  const total = daily.reduce((sum, day) => sum + day.count, 0);
  const firstActive = daily.findIndex((day) => day.count > 0);
  const activeSpan = firstActive === -1 ? 0 : daily.length - firstActive;
  const average = activeSpan ? Math.round(total / activeSpan) : 0;
  const bounds = [1, 2, 3].map((step) => Math.ceil((max * step) / 4));

  return (
    <section className="card hmc" aria-label={t("每天存下的作品数")}>
      <div className="row-h top">
        <div>
          <h2 className="h4">{t("每天存下的作品数")}</h2>
          <p className="cap">{t("最近 10 周 · 共 {n} 个", { n: formatInteger(total) })}</p>
        </div>
        <span className="sp" />
        <a className="circ" href={routeHref({ name: "library", filters: { downloaded: true } })} aria-label={t("查看已存到 NAS 的作品")}>
          <ArrowUpRight size={14} />
        </a>
      </div>
      <div className="legend">
        {max >= 4 ? (
          <>
            <span>
              <i className="l1" />≤ {formatInteger(bounds[0])}
            </span>
            <span>
              <i className="l2" />≤ {formatInteger(bounds[1])}
            </span>
            <span>
              <i className="l3" />≤ {formatInteger(bounds[2])}
            </span>
            <span>
              <i className="l4" />≤ {formatInteger(max)}
            </span>
          </>
        ) : (
          <>
            <span>{t("少")}</span>
            <span className="legend-ramp">
              <i className="l1" />
              <i className="l2" />
              <i className="l3" />
              <i className="l4" />
            </span>
            <span>{t("多")}</span>
          </>
        )}
      </div>
      <div className="hm" role="img" aria-label={t("最近 10 周每天存下的作品数热力图")}>
        {WEEKDAYS.map((label, row) => (
          <div className="hm-row" key={label}>
            <span className="hm-l">{label}</span>
            {columns.map((column, col) => {
              const cell = column.cells[row];
              if (!cell) return <i key={col} className="l0" />;
              if (cell.future) return <i key={col} className="lf" />;
              return <i key={col} className={`l${cell.level}`} title={t("{date}：存下 {n} 个", { date: cell.date.slice(5).replace("-", "月") + "日", n: cell.count })} />;
            })}
          </div>
        ))}
        <div className="hm-row hm-x">
          <span />
          {columns.map((column, col) => (
            <span key={col}>{column.month ?? ""}</span>
          ))}
        </div>
      </div>
      <div className="hm-stats">
        <div>
          <b className="num">{formatInteger(average)}</b>
          <span>{t("日均存下")}</span>
        </div>
        <div>
          <b className="num">{formatInteger(max)}</b>
          <span>{t("单日最多")}</span>
        </div>
        <div>
          <b className="num">{t("{n} 天", { n: savingStreak(daily) })}</b>
          <span>{t("连续不间断")}</span>
        </div>
      </div>
    </section>
  );
}
