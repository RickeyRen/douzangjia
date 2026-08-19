import { Gear, House, MagnifyingGlass, Pulse, Stack } from "@phosphor-icons/react";

import { useI18n } from "../../i18n/context";

export type MobileDestination = "feed" | "collections" | "search" | "activity" | "settings";

export function MobileNavigation({ onOpen }: { onOpen: (destination: MobileDestination) => void }) {
  const { t } = useI18n();
  const destinations = [
    { id: "feed" as const, label: t("mobileFeed"), icon: House },
    { id: "collections" as const, label: t("mobileCollections"), icon: Stack },
    { id: "search" as const, label: t("mobileSearch"), icon: MagnifyingGlass },
    { id: "activity" as const, label: t("mobileActivity"), icon: Pulse },
    { id: "settings" as const, label: t("settings"), icon: Gear },
  ];

  return (
    <nav aria-label={t("mobileNavigation")} className="iphone-bottom-nav friendly-mobile-nav">
      {destinations.map(({ id, label, icon: Icon }) => (
        <button key={id} type="button" aria-label={label} onClick={() => onOpen(id)} className="touch-target mobile-navigation-item">
          <Icon size={21} weight="regular" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
