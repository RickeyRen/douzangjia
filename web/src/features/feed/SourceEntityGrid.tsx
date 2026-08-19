import { MusicNotes } from "@phosphor-icons/react";

import type { SourceEntity } from "../../app/api";
import { useI18n } from "../../i18n/context";

export function SourceEntityGrid({ entities }: { entities: SourceEntity[] }) {
  const { t } = useI18n();
  return (
    <div data-testid="source-entity-grid" className="source-entity-grid">
      {entities.map((entity) => {
        const duration = typeof entity.metadata.duration === "string" ? entity.metadata.duration : null;
        const content = (
          <>
            <span className="source-entity-cover">
              {entity.coverUrl ? <img src={entity.coverUrl} alt="" loading="lazy" draggable={false} /> : <MusicNotes size={30} weight="duotone" />}
              <span className="source-entity-type"><MusicNotes size={15} weight="fill" />{t("musicLabel")}</span>
            </span>
            <span className="source-entity-copy">
              <strong>{entity.title}</strong>
              <small>{entity.subtitle || t("favoriteMusicFallback")}{duration ? ` · ${duration}` : ""}</small>
            </span>
          </>
        );
        return entity.sourceUrl ? (
          <a key={entity.id} className="source-entity-card" href={entity.sourceUrl} target="_blank" rel="noreferrer" aria-label={`${t("openMusicPrefix")}${entity.title}`}>
            {content}
          </a>
        ) : (
          <article key={entity.id} className="source-entity-card">{content}</article>
        );
      })}
    </div>
  );
}
