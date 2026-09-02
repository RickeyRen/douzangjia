import { Pulse } from "@phosphor-icons/react";
import type { ReactNode } from "react";

import type { MetricPoint } from "../../app/api";

export type DashboardTone = "blue" | "cyan" | "green" | "amber" | "violet" | "rose";

export function DashboardSection({
  title,
  children,
  className = "",
  testId,
}: {
  title: string;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <section className={`home-dashboard-section ${className}`.trim()} data-testid={testId}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export function DashboardMetric({
  label,
  value,
  detail,
  icon,
  tone,
  onClick,
}: {
  label: string;
  value: string;
  detail?: ReactNode;
  icon: ReactNode;
  tone: DashboardTone;
  onClick?: () => void;
}) {
  const content = (
    <>
      <span className="app-icon-well home-dashboard-icon" data-icon-tone={tone}>{icon}</span>
      <span className="home-dashboard-metric-copy">
        <small>{label}</small>
        <strong>{value}</strong>
        {detail === undefined ? null : <span>{detail}</span>}
      </span>
    </>
  );
  return onClick ? (
    <button className="home-dashboard-metric" type="button" onClick={onClick}>{content}</button>
  ) : (
    <article className="home-dashboard-metric">{content}</article>
  );
}

function linePoints(values: number[], width = 600, height = 112): string {
  if (values.length === 0) return "";
  const maximum = Math.max(...values, 1);
  return values.map((value, index) => {
    const x = values.length === 1 ? width : (index / (values.length - 1)) * width;
    const y = height - (value / maximum) * (height - 18) - 9;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

export function DashboardTrend({
  label,
  points,
  value,
  current,
  tone,
  emptyLabel,
}: {
  label: string;
  points: MetricPoint[];
  value: (point: MetricPoint) => number;
  current: string;
  tone: "blue" | "violet";
  emptyLabel: string;
}) {
  const values = points.map(value);
  return (
    <article className="home-trend" data-chart-tone={tone}>
      <header>
        <div><span>{label}</span><strong>{current}</strong></div>
        <span className="app-icon-well home-dashboard-icon" data-icon-tone={tone}><Pulse size={18} weight="duotone" /></span>
      </header>
      {values.length === 0 ? <p>{emptyLabel}</p> : (
        <svg role="img" aria-label={label} viewBox="0 0 600 112" preserveAspectRatio="none">
          <path d="M0 28H600M0 56H600M0 84H600" />
          <polyline points={linePoints(values)} fill="none" />
        </svg>
      )}
    </article>
  );
}
