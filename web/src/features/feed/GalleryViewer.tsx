import { useState } from "react";

import type { MediaFile } from "../../app/api";
import { useI18n } from "../../i18n/context";

export function GalleryViewer({ media, description }: { media: MediaFile[]; description: string }) {
  const { t } = useI18n();
  const [index, setIndex] = useState(0);
  return (
    <div className="gallery-viewer">
      <div
        className="gallery-strip snap-x snap-mandatory"
        onScroll={(event) => {
          const width = event.currentTarget.clientWidth;
          if (width) setIndex(Math.round(event.currentTarget.scrollLeft / width));
        }}
      >
        {media.map((file) => (
          <img key={file.id} className="gallery-image snap-center" src={file.url} alt={description} loading="lazy" />
        ))}
      </div>
      <div className="gallery-position" aria-label={t("galleryPosition")}>
        {media.map((file, position) => (
          <span key={file.id} className={position === index ? "is-active" : ""} />
        ))}
      </div>
    </div>
  );
}
