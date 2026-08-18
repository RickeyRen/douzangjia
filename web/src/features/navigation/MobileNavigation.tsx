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
    <nav aria-label={t("mobileNavigation")} className="iphone-bottom-nav fixed inset-x-0 bottom-0 z-[4] hidden grid-cols-5 border-t border-white/10 bg-[#111419]/94 px-2 pb-[max(8px,env(safe-area-inset-bottom))] pt-2 shadow-[inset_0_1px_0_rgba(255,255,255,.06)] backdrop-blur-xl max-lg:grid">
      {destinations.map(({ id, label, icon: Icon }) => (
        <button key={id} type="button" onClick={() => onOpen(id)} className="touch-target grid min-h-12 place-items-center gap-0.5 rounded-xl px-1 text-[10px] text-[#b1b6bf] transition-[transform,color,background-color] active:scale-[.96] active:bg-white/[.06]">
          <Icon size={21} weight="regular" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}
