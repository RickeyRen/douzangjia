import { ArrowsClockwise, MagnifyingGlass, Play } from "@phosphor-icons/react";
import { useMemo, useState, type ReactNode } from "react";

import type { DurationBucket, FeedQuery, FeedSort, PeriodBucket } from "../app/api";
import type { LibraryFilters } from "../app/router";
import { useFeed } from "../lib/useFeed";
import { EmptyState, ErrorState, Segmented, Select } from "../ui/primitives";
import { MediaGrid } from "./MediaGrid";
import { Player } from "./Player";
import { useMediaNavigation } from "./useMediaNavigation";

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
  const navigation = useMediaNavigation();

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
          label="作品类型"
          value={filters.type ?? "all"}
          options={[
            { value: "all", label: "全部" },
            { value: "video", label: "视频" },
            { value: "gallery", label: "图集" },
          ]}
          onChange={(value) => update({ type: value === "all" ? undefined : value })}
        />
        <Select<FeedSort> label="排序方式" value={sort} options={sorts.map((value) => ({ value, label: SORT_LABELS[value] }))} onChange={(value) => update({ sort: value })} />
        <Select<"all" | DurationBucket>
          label="时长"
          value={filters.duration ?? "all"}
          options={(Object.keys(DURATION_LABELS) as Array<"all" | DurationBucket>).map((value) => ({ value, label: DURATION_LABELS[value] }))}
          onChange={(value) => update({ duration: value === "all" ? undefined : value })}
        />
        <Select<"all" | PeriodBucket>
          label="收藏时间"
          value={filters.period ?? "all"}
          options={(Object.keys(PERIOD_LABELS) as Array<"all" | PeriodBucket>).map((value) => ({ value, label: PERIOD_LABELS[value] }))}
          onChange={(value) => update({ period: value === "all" ? undefined : value })}
        />
        <button type="button" className="chip" aria-pressed={Boolean(filters.downloaded)} onClick={() => update({ downloaded: filters.downloaded ? undefined : true })}>
          仅看已存到 NAS
        </button>
        {sort === "random" ? (
          <button type="button" className="chip" onClick={() => setSeed(1 + Math.floor(Math.random() * 65_000))}>
            <ArrowsClockwise size={15} weight="bold" />
            换一批
          </button>
        ) : null}
        <span className="toolbar-spacer" />
        <button type="button" className="btn btn-primary btn-sm" disabled={feed.items.length === 0} onClick={() => setPlaying(0)}>
          <Play size={14} weight="fill" />
          播放
        </button>
      </div>

      {feed.error && feed.items.length === 0 ? (
        <ErrorState onRetry={feed.retry} />
      ) : !feed.loading && feed.items.length === 0 ? (
        filtered ? (
          <EmptyState
            icon={<MagnifyingGlass size={40} weight="duotone" />}
            title="没有符合条件的作品"
            body="换个筛选条件试试。"
            action={
              <button type="button" className="btn btn-secondary" onClick={() => onFiltersChange({ sort: filters.sort })}>
                清除筛选
              </button>
            }
          />
        ) : (
          empty ?? <EmptyState icon={<MagnifyingGlass size={40} weight="duotone" />} title="这里还没有作品" />
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
        />
      )}

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
