import type { ButtonHTMLAttributes, ReactNode } from "react";

type FriendlyButtonTone = "primary" | "secondary" | "danger";

type FriendlyButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  fullWidth?: boolean;
  tone?: FriendlyButtonTone;
};

export function FriendlyButton({
  children,
  className = "",
  fullWidth = false,
  tone = "secondary",
  type = "button",
  ...props
}: FriendlyButtonProps) {
  return (
    <button
      type={type}
      className={`friendly-button friendly-button-${tone}${fullWidth ? " friendly-button-full" : ""} ${className}`.trim()}
      {...props}
    >
      {children}
    </button>
  );
}
