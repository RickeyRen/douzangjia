import type { ReactNode } from "react";

export function AppShell({
  primary,
  context,
  children,
  details,
}: {
  primary: ReactNode;
  context: ReactNode;
  children: ReactNode;
  details?: ReactNode;
}) {
  return (
    <div
      className="credit-pros-shell"
      data-has-details={details ? "true" : "false"}
      data-testid="credit-pros-shell"
    >
      <div className="credit-pros-primary" data-testid="app-primary-rail">{primary}</div>
      <div className="credit-pros-context" data-testid="app-context-rail">{context}</div>
      <div className="credit-pros-stage" data-testid="app-main-stage">{children}</div>
      {details ? <div className="credit-pros-details" data-testid="app-details-rail">{details}</div> : null}
    </div>
  );
}
