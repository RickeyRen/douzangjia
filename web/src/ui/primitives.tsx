import { CaretDown, CircleNotch, WarningCircle } from "@phosphor-icons/react";
import { useState, type ReactNode } from "react";
import { t } from "../i18n/t";

export function Avatar({ src, name, size }: { src?: string | null; name?: string | null; size?: number }) {
  const [failed, setFailed] = useState(false);
  const initial = (name ?? "").trim().slice(0, 1) || "?";
  const style = size ? { width: size, height: size, fontSize: Math.round(size * 0.38) } : undefined;
  return (
    <span className="avatar" style={style} aria-hidden="true">
      {src && !failed ? <img src={src} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} /> : initial}
    </span>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((option) => (
        <button key={option.value} type="button" aria-pressed={option.value === value} onClick={() => onChange(option.value)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Select<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <label className="select">
      <span className="sr-only">{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value as T)}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <CaretDown size={13} weight="bold" />
    </label>
  );
}

export function Switch({ checked, onChange, label, disabled }: { checked: boolean; onChange: (checked: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      className="switch"
      onClick={() => onChange(!checked)}
    />
  );
}

export function Spinner({ size = 18 }: { size?: number }) {
  return <CircleNotch className="spinner" size={size} weight="bold" aria-hidden="true" />;
}

export function EmptyState({ icon, title, body, action }: { icon: ReactNode; title: string; body?: string; action?: ReactNode }) {
  return (
    <div className="state">
      <div>
        {icon}
        <h2>{title}</h2>
        {body ? <p>{body}</p> : null}
        {action}
      </div>
    </div>
  );
}

export function ErrorState({ onRetry, message = t("加载失败，请检查 NAS 服务是否正常。") }: { onRetry: () => void; message?: string }) {
  return (
    <EmptyState
      icon={<WarningCircle size={40} weight="duotone" />}
      title={t("出了点问题")}
      body={message}
      action={
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          {t("重试")}
        </button>
      }
    />
  );
}

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-header">
      <div>
        <h1>{title}</h1>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {actions ? <div className="page-actions">{actions}</div> : null}
    </header>
  );
}

export function Progress({ value, tone }: { value: number; tone?: "success" | "info" | "warning" }) {
  const width = `${Math.max(0, Math.min(100, value))}%`;
  return (
    <div className={`progress${tone ? ` progress-${tone}` : ""}`} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value)}>
      <span style={{ width }} />
    </div>
  );
}
