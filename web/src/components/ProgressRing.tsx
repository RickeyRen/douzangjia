import type { CSSProperties } from "react";

export type ProgressRingState = "determinate" | "running" | "complete" | "failed" | "idle";

function normalizedProgress(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.round(Math.min(100, Math.max(0, value)));
}

export function ProgressRing({
  value = 0,
  label,
  state = "determinate",
  compact = false,
}: {
  value?: number;
  label: string;
  state?: ProgressRingState;
  compact?: boolean;
}) {
  const progress = state === "complete" ? 100 : normalizedProgress(value);
  const indeterminate = state === "running";
  const center = state === "complete" ? "✓" : state === "failed" ? "!" : state === "idle" ? "–" : `${progress}`;

  return (
    <span
      role="progressbar"
      aria-label={label}
      aria-valuemin={indeterminate ? undefined : 0}
      aria-valuemax={indeterminate ? undefined : 100}
      aria-valuenow={indeterminate ? undefined : progress}
      className={`progress-ring progress-ring-${state}${compact ? " is-compact" : ""}`}
      style={{ "--progress-ring-value": progress } as CSSProperties}
      title={indeterminate ? label : `${label} · ${progress}%`}
    >
      <span className="progress-ring-graphic" aria-hidden="true">
        <svg viewBox="0 0 36 36">
          <circle className="progress-ring-track" cx="18" cy="18" r="15" pathLength="100" />
          <circle className="progress-ring-meter" cx="18" cy="18" r="15" pathLength="100" />
        </svg>
      </span>
      <span className="progress-ring-value" aria-hidden="true">{center}</span>
    </span>
  );
}
