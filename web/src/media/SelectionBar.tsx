import { CloudArrowDown, FolderPlus, Star, X } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { archiveSelection, bulkStar, type FeedItem } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { Spinner } from "../ui/primitives";
import { AlbumPicker } from "./Organize";

export function SelectionBar({
  items,
  selected,
  onSelectAll,
  onClear,
  onItemsPatched,
}: {
  items: FeedItem[];
  selected: Set<string>;
  onSelectAll: () => void;
  onClear: () => void;
  onItemsPatched: (ids: string[], patch: Partial<FeedItem>) => void;
}) {
  const { toast } = useAppData();
  const [albumOpen, setAlbumOpen] = useState(false);
  const [busy, setBusy] = useState<"star" | "download" | null>(null);
  const ids = [...selected];
  const chosen = items.filter((item) => selected.has(item.awemeId));
  const allStarred = chosen.length > 0 && chosen.every((item) => item.starred);
  const notOnNas = chosen.filter((item) => item.local.state !== "downloaded").length;

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClear();
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "a") {
        const target = event.target as HTMLElement | null;
        if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
        event.preventDefault();
        onSelectAll();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClear, onSelectAll]);

  async function star() {
    setBusy("star");
    try {
      await bulkStar(ids, !allStarred);
      onItemsPatched(ids, { starred: !allStarred });
      toast(allStarred ? `已取消 ${ids.length} 个精选` : `已精选 ${ids.length} 个作品`);
    } catch {
      toast("操作失败");
    } finally {
      setBusy(null);
    }
  }

  async function download() {
    setBusy("download");
    try {
      const result = await archiveSelection(ids);
      toast(result.skipped ? `已加入下载，${result.skipped} 个暂时拿不到媒体信息` : "已加入下载队列");
      onItemsPatched(
        chosen.filter((item) => item.local.state !== "downloaded").map((item) => item.awemeId),
        { local: { state: "waiting", readyAssets: 0, totalAssets: 1, downloadedBytes: 0, totalBytes: null } },
      );
    } catch {
      toast("加入下载队列失败");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="selection-bar" role="toolbar" aria-label="批量操作">
      <strong className="num">已选 {ids.length} 个</strong>
      <button type="button" className="btn btn-ghost btn-sm" onClick={onSelectAll}>
        全选已加载
      </button>
      <span className="toolbar-spacer" />
      <span className="popover-anchor selection-album">
        <button type="button" className="btn btn-secondary btn-sm" disabled={!ids.length} aria-expanded={albumOpen} onClick={() => setAlbumOpen((value) => !value)}>
          <FolderPlus size={15} weight="bold" />
          加入相册
        </button>
        {albumOpen ? <AlbumPicker itemIds={ids} onClose={() => setAlbumOpen(false)} /> : null}
      </span>
      <button type="button" className="btn btn-secondary btn-sm" disabled={!ids.length || busy !== null} onClick={() => void star()}>
        {busy === "star" ? <Spinner size={14} /> : <Star size={15} weight={allStarred ? "fill" : "bold"} />}
        {allStarred ? "取消精选" : "精选"}
      </button>
      <button type="button" className="btn btn-primary btn-sm" disabled={!notOnNas || busy !== null} onClick={() => void download()}>
        {busy === "download" ? <Spinner size={14} /> : <CloudArrowDown size={15} weight="bold" />}
        存到 NAS{notOnNas ? ` (${notOnNas})` : ""}
      </button>
      <button type="button" className="icon-btn" aria-label="退出选择" onClick={onClear}>
        <X size={18} weight="bold" />
      </button>
    </div>
  );
}
