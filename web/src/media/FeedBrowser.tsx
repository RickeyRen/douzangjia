import { ArrowsClockwise, CheckSquare, Crop, GridFour, MagnifyingGlass, Play, SquaresFour } from "@phosphor-icons/react";
import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";

import type { DurationBucket, FeedItem, FeedQuery, FeedSort, PeriodBucket } from "../app/api";
import type { LibraryFilters } from "../app/router";
import { useFeed } from "../lib/useFeed";
import { useGridPrefs } from "../lib/useGridPrefs";
import { EmptyState, ErrorState, Segmented, Select } from "../ui/primitives";
import { MediaGrid } from "./MediaGrid";
import { Player } from "./Player";
import { SelectionBar } from "./SelectionBar";
import { useMediaNavigation } from "./useMediaNavigation";
import { t } from "../i18n/t";

const DURATION_LABELS: Record<"all" | DurationBucket, string> = { all: "任意时长", short: "1 分钟内", medium: "1–5 分钟", long: "5 分钟以上" };
const PERIOD_LABELS: Record<"all" | PeriodBucket, string> = { all: "任意时间", week: "最近一周", month: "最近一月", quarter: "最近三月", year: "今年" };

const SORT_LABELS: Record<FeedSort, string> = {
  relevance: "最相关",
  source: "收藏顺序",
  album: "加入顺序",
  starred: "精选时间",
  archived: "最近收藏",
  published: "最新发布",
  random: "随机",
};

type TypeFilter = "all" | "video" | "gallery";

export function FeedBrowser({
  base,
  filters,
  sorts,
  onFiltersChange,
  empty,
  showMeta = true,
}: {
  base: Omit<FeedQuery, "sort" | "type" | "downloaded" | "cursor" | "seed" | "duration" | "period">;
  filters: LibraryFilters;
  /** Allowed sorts; the first one is the default. */
  sorts: FeedSort[];
  onFiltersChange: (filters: LibraryFilters) => void;
  empty?: ReactNode;
  showMeta?: boolean;
}) {
  const sort = filters.sort && sorts.includes(filters.sort) ? filters.sort : sorts[0];
  const [seed, setSeed] = useState(() => 1 + Math.floor(Math.random() * 65_000));
  const query = useMemo<FeedQuery>(
    () => ({ ...base, sort, seed, type: filters.type, downloaded: filters.downloaded, duration: filters.duration, period: filters.period }),
    [base, filters.downloaded, filters.duration, filters.period, filters.type, seed, sort],
  );
  const feed = useFeed(query);
  const [playing, setPlaying] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<string> | null>(null);
  const [gridPrefs, setGridPrefs] = useGridPrefs();
  const anchor = useRef<number | null>(null);
  const navigation = useMediaNavigation();

  const toggleSelect = useCallback(
    (index: number, range: boolean) => {
      const items = feed.items;
      setSelected((current) => {
        const next = new Set(current ?? []);
        if (range && anchor.current !== null) {
          const [from, to] = [Math.min(anchor.current, index), Math.max(anchor.current, index)];
          for (let position = from; position <= to; position += 1) next.add(items[position].awemeId);
        } else {
          const id = items[index].awemeId;
          if (next.has(id)) next.delete(id);
          else next.add(id);
          anchor.current = index;
        }
        return next;
      });
    },
    [feed.items],
  );
  const selectAll = useCallback(() => setSelected(new Set(feed.items.map((item) => item.awemeId))), [feed.items]);
  const clearSelection = useCallback(() => {
    setSelected(null);
    anchor.current = null;
  }, []);
  const patchMany = useCallback(
    (ids: string[], patch: Partial<FeedItem>) => {
      for (const id of ids) feed.updateItem(id, patch);
    },
    [feed],
  );

  function update(patch: Partial<LibraryFilters>) {
    const next = { ...filters, ...patch };
    if (next.sort === sorts[0]) delete next.sort;
    onFiltersChange(next);
  }

  const filtered = Boolean(filters.type || filters.downloaded || filters.duration || filters.period);

  return (
    <>
      <div className="toolbar">
        <Segmented<TypeFilter>
          label={t("作品类型")}
          value={filters.type ?? "all"}
          options={[
            { value: "all", label: t("全部") },
            { value: "video", label: t("视频") },
            { value: "gallery", label: t("图集") },
          ]}
          onChange={(value) => update({ type: value === "all" ? undefined : value })}
        />
        <Select<FeedSort> label={t("排序方式")} value={sort} options={sorts.map((value) => ({ value, label: SORT_LABELS[value] }))} onChange={(value) => update({ sort: value })} />
        <Select<"all" | DurationBucket>
          label={t("时长")}
          value={filters.duration ?? "all"}
          options={(Object.keys(DURATION_LABELS) as Array<"all" | DurationBucket>).map((value) => ({ value, label: DURATION_LABELS[value] }))}
          onChange={(value) => update({ duration: value === "all" ? undefined : value })}
        />
        <Select<"all" | PeriodBucket>
          label={t("收藏时间")}
          value={filters.period ?? "all"}
          options={(Object.keys(PERIOD_LABELS) as Array<"all" | PeriodBucket>).map((value) => ({ value, label: PERIOD_LABELS[value] }))}
          onChange={(value) => update({ period: value === "all" ? undefined : value })}
        />
        <button type="button" className="chip" aria-pressed={Boolean(filters.downloaded)} onClick={() => update({ downloaded: filters.downloaded ? undefined : true })}>
          {t("仅看已存到 NAS")}
        </button>
        {sort === "random" ? (
          <button type="button" className="chip" onClick={() => setSeed(1 + Math.floor(Math.random() * 65_000))}>
            <ArrowsClockwise size={15} weight="bold" />
            {t("换一批")}
          </button>
        ) : null}
        <span className="toolbar-spacer" />
        <span className="seg seg-icons" role="group" aria-label={t("网格密度")}>
          <button type="button" aria-label={t("舒适")} title={t("舒适")} aria-pressed={gridPrefs.density === "comfortable"} onClick={() => setGridPrefs({ density: "comfortable" })}>
            <SquaresFour size={16} />
          </button>
          <button type="button" aria-label={t("紧凑")} title={t("紧凑")} aria-pressed={gridPrefs.density === "compact"} onClick={() => setGridPrefs({ density: "compact" })}>
            <GridFour size={16} />
          </button>
        </span>
        <button type="button" className="icon-btn" aria-label={gridPrefs.aspect === "natural" ? t("切换为统一裁切") : t("切换为原始比例")} title={gridPrefs.aspect === "natural" ? t("原始比例") : t("统一裁切")} aria-pressed={gridPrefs.aspect === "natural"} onClick={() => setGridPrefs({ aspect: gridPrefs.aspect === "natural" ? "crop" : "natural" })}>
          <Crop size={17} weight={gridPrefs.aspect === "natural" ? "fill" : "regular"} />
        </button>
        <button type="button" className={`btn btn-secondary btn-sm${selected ? " is-active" : ""}`} aria-pressed={selected !== null} disabled={feed.items.length === 0} onClick={() => (selected ? clearSelection() : setSelected(new Set()))}>
          <CheckSquare size={15} weight={selected ? "fill" : "bold"} />
          {selected ? t("完成") : t("选择")}
        </button>
        <button type="button" className="btn btn-primary btn-sm" disabled={feed.items.length === 0} onClick={() => setPlaying(0)}>
          <Play size={14} weight="fill" />
          {t("播放")}
        </button>
      </div>

      {feed.error && feed.items.length === 0 ? (
        <ErrorState onRetry={feed.retry} />
      ) : !feed.loading && feed.items.length === 0 ? (
        filtered ? (
          <EmptyState
            icon={<MagnifyingGlass size={40} weight="duotone" />}
            title={t("没有符合条件的作品")}
            body="换个筛选条件试试。"
            action={
              <button type="button" className="btn btn-secondary" onClick={() => onFiltersChange({ sort: filters.sort })}>
                {t("清除筛选")}
              </button>
            }
          />
        ) : (
          empty ?? <EmptyState icon={<MagnifyingGlass size={40} weight="duotone" />} title={t("这里还没有作品")} />
        )
      ) : (
        <MediaGrid
          items={feed.items}
          loading={feed.loading}
          loadingMore={feed.loadingMore}
          hasMore={feed.hasMore}
          error={feed.error}
          onLoadMore={() => void feed.loadMore()}
          onRetry={feed.retry}
          onOpen={setPlaying}
          onOpenCreator={navigation.openCreator}
          showMeta={showMeta}
          selected={selected ?? undefined}
          onToggleSelect={toggleSelect}
        />
      )}

      {selected ? <SelectionBar items={feed.items} selected={selected} onSelectAll={selectAll} onClear={clearSelection} onItemsPatched={patchMany} /> : null}

      {playing !== null ? (
        <Player
          items={feed.items}
          index={playing}
          onIndexChange={setPlaying}
          onClose={() => setPlaying(null)}
          hasMore={feed.hasMore}
          onLoadMore={() => void feed.loadMore()}
          onItemPatch={feed.updateItem}
          {...navigation.playerProps(() => setPlaying(null))}
        />
      ) : null}
    </>
  );
}
