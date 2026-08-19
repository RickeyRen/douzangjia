import type { ButtonHTMLAttributes, ReactNode } from "react";

type FriendlyIconButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "aria-label"
> & {
  children: ReactNode;
  label: string;
};

export function FriendlyIconButton({
  children,
  className = "",
  label,
  type = "button",
  ...props
}: FriendlyIconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      className={`friendly-icon-button ${className}`.trim()}
      {...props}
    >
      {children}
    </button>
  );
}
