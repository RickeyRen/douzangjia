import { Ghost } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";

import { fetchVanishedCreators, type Creator, type CreatorArchiveStatus } from "../app/api";
import { routeHref } from "../app/router";
import { t } from "../i18n/t";
import { ARCHIVE_STATUS_LABEL } from "../lib/creatorArchive";
import { formatDate, formatInteger } from "../lib/format";
import { Avatar, EmptyState, ErrorState, PageHeader, Segmented, Spinner } from "../ui/primitives";

type Filter = "all" | Exclude<CreatorArchiveStatus, "active">;

export function VanishedPage() {
  const [creators, setCreators] = useState<Creator[] | null>(null);
  const [counts, setCounts] = useState<Partial<Record<CreatorArchiveStatus, number>>>({});
  const [cursor, setCursor] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    let active = true;
    setCreators(null);
    setError(false);
    fetchVanishedCreators()
      .then((page) => {
        if (!active) return;
        setCreators(page.items);
        setCounts(page.counts);
        setCursor(page.nextCursor);
      })
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, [attempt]);

  async function loadMore() {
    if (!cursor) return;
    setLoadingMore(true);
    try {
      const page = await fetchVanishedCreators(cursor);
      setCreators((current) => [...(current ?? []), ...page.items]);
      setCursor(page.nextCursor);
    } finally {
      setLoadingMore(false);
    }
  }

  const total = Object.values(counts).reduce((sum, value) => sum + (value ?? 0), 0);
  const options = useMemo(
    () => [
      { value: "all" as Filter, label: t("全部 {n}", { n: total }) },
      ...(Object.keys(ARCHIVE_STATUS_LABEL) as Array<Exclude<Filter, "all">>)
        .filter((status) => counts[status])
        .map((status) => ({ value: status, label: `${ARCHIVE_STATUS_LABEL[status]} ${counts[status]}` })),
    ],
    [counts, total],
  );
  const visible = (creators ?? []).filter((creator) => filter === "all" || creator.archive?.status === filter);

  return (
    <>
      <PageHeader
        title={t("消失的博主")}
        subtitle={t("被封号、资料被重置或注销的博主，这里保留着他们原来的样子和你存下的作品")}
      />
      {options.length > 2 ? (
        <div className="toolbar">
          <Segmented label={t("按状态筛选")} value={filter} options={options} onChange={setFilter} />
        </div>
      ) : null}
      {error ? (
        <ErrorState onRetry={() => setAttempt((value) => value + 1)} />
      ) : creators === null ? (
        <div className="state">
          <Spinner size={24} />
        </div>
      ) : creators.length === 0 ? (
        <EmptyState
          icon={<Ghost size={40} weight="duotone" />}
          title={t("还没有发现消失的博主")}
          body={t("后台会慢慢检查你收藏过的博主，一旦有人被封号或资料被重置，就会出现在这里。")}
        />
      ) : (
        <>
          <div className="vanished-grid">
            {visible.map((creator) => (
              <VanishedCard key={creator.id} creator={creator} />
            ))}
          </div>
          {cursor ? (
            <div className="grid-footer">
              <button type="button" className="btn btn-secondary btn-sm" disabled={loadingMore} onClick={() => void loadMore()}>
                {loadingMore ? <Spinner size={14} /> : null}
                {t("加载更多")}
              </button>
            </div>
          ) : null}
        </>
      )}
    </>
  );
}

function VanishedCard({ creator }: { creator: Creator }) {
  const archive = creator.archive;
  const status = archive && archive.status !== "active" ? archive.status : null;
  const cover = archive?.preserved?.coverUrl;
  const renamed = archive && archive.currentNickname !== creator.nickname ? archive.currentNickname : null;
  return (
    <a className="vanished-card" href={routeHref({ name: "creator", creatorId: creator.id, filters: {} })}>
      <div className="vanished-cover" style={cover ? { backgroundImage: `url(${cover})` } : undefined} />
      <div className="vanished-body">
        <Avatar src={creator.avatarUrl} name={creator.nickname} />
        <div className="vanished-text">
          <strong>{creator.nickname}</strong>
          <small>{creator.uniqueId ? t("抖音号 {id}", { id: creator.uniqueId }) : t("抖音号未知")}</small>
          {renamed ? <small className="vanished-now">{t("现在显示为 {name}", { name: renamed })}</small> : null}
        </div>
      </div>
      <div className="vanished-meta">
        {status ? <span className={`vanished-pill vanished-${status}`}>{ARCHIVE_STATUS_LABEL[status]}</span> : null}
        <span>
          {t("{known} 个作品 · 已存 {saved}", {
            known: formatInteger(creator.knownItemCount),
            saved: formatInteger(creator.archivedItemCount),
          })}
        </span>
        {archive?.since ? <span>{t("发现于 {date}", { date: formatDate(archive.since) })}</span> : null}
      </div>
    </a>
  );
}
