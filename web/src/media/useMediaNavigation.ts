import { useCallback } from "react";

import { navigate } from "../app/router";

/** Navigation shared by tiles and the player: creator pages, tag search, sources. */
export function useMediaNavigation() {
  const openCreator = useCallback((creatorId: string | null, name: string) => {
    if (creatorId) navigate({ name: "creator", creatorId, filters: {} });
    else navigate({ name: "search", query: name, filters: {} });
  }, []);

  const playerProps = useCallback(
    (close: () => void) => ({
      onOpenCreator: (creatorId: string | null, name: string) => {
        close();
        openCreator(creatorId, name);
      },
      onSearch: (term: string) => {
        close();
        navigate({ name: "search", query: term, filters: {} });
      },
      onOpenSource: (sourceId: string) => {
        close();
        navigate({ name: "library", sourceId, filters: {} });
      },
    }),
    [openCreator],
  );

  return { openCreator, playerProps };
}
