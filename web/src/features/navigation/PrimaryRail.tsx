import {
  Gear,
  House,
  MagnifyingGlass,
  Pulse,
  Stack,
  TiktokLogo,
  UserCircle,
} from "@phosphor-icons/react";

import type { DashboardSnapshot } from "../../app/api";
import { useI18n } from "../../i18n/context";
import type { MobileDestination } from "./MobileNavigation";

type PrimaryDestination = "home" | "library" | "search" | "activity" | "settings";

const targetFor: Record<PrimaryDestination, MobileDestination> = {
  home: "feed",
  library: "collections",
  search: "search",
  activity: "activity",
  settings: "settings",
};

export function PrimaryRail({
  active,
  dashboard,
  onOpen,
}: {
  active: "home" | "library";
  dashboard: DashboardSnapshot | null;
  onOpen: (destination: MobileDestination) => void;
}) {
  const { t } = useI18n();
  const destinations = [
    { id: "home" as const, label: t("home"), icon: House, tone: "amber" },
    { id: "library" as const, label: t("allArchives"), icon: Stack, tone: "blue" },
    { id: "search" as const, label: t("mobileSearch"), icon: MagnifyingGlass, tone: "violet" },
    { id: "activity" as const, label: t("mobileActivity"), icon: Pulse, tone: "green" },
    { id: "settings" as const, label: t("settings"), icon: Gear, tone: "cyan" },
  ];
  const account = dashboard?.account.account;
  const health = dashboard?.account.status ?? "unknown";

  return (
    <nav className="primary-rail" aria-label={`${t("brand")} · ${t("mobileNavigation")}`}>
      <div className="primary-brand" aria-label={t("brand")}><TiktokLogo size={24} weight="fill" /></div>
      <div className="primary-destinations">
        {destinations.map(({ id, label, icon: Icon, tone }) => (
          <button
            key={id}
            type="button"
            aria-label={`${t("brand")} · ${label}`}
            aria-current={active === id ? "page" : undefined}
            data-icon-tone={tone}
            onClick={() => onOpen(targetFor[id])}
          >
            <Icon size={21} weight={active === id ? "fill" : "regular"} />
            <span>{label}</span>
          </button>
        ))}
      </div>
      <div className="primary-account" data-health={health} title={account?.nickname ?? t("brand")}>
        {account?.avatarUrl ? <img src={account.avatarUrl} alt="" /> : <UserCircle size={25} weight="duotone" />}
        <i aria-hidden="true" />
      </div>
    </nav>
  );
}
