import { useState } from "react";

import type { MediaFile } from "../../app/api";
import { useI18n } from "../../i18n/context";

export function GalleryViewer({ media, description }: { media: MediaFile[]; description: string }) {
  const { t } = useI18n();
  const [index, setIndex] = useState(0);
  return (
    <div className="relative h-full w-full overflow-hidden">
      <div
        className="gallery-strip flex h-full snap-x snap-mandatory overflow-x-auto"
        onScroll={(event) => {
          const width = event.currentTarget.clientWidth;
          if (width) setIndex(Math.round(event.currentTarget.scrollLeft / width));
        }}
      >
        {media.map((file) => (
          <img key={file.id} className="h-full min-w-full snap-center object-contain" src={file.url} alt={description} loading="lazy" />
        ))}
      </div>
      <div className="absolute left-1/2 top-4 flex -translate-x-1/2 gap-1.5" aria-label={t("galleryPosition")}>
        {media.map((file, position) => (
          <span key={file.id} className={`h-1 rounded-full transition-all ${position === index ? "w-5 bg-white" : "w-1.5 bg-white/40"}`} />
        ))}
      </div>
    </div>
  );
}
