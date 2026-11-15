import { CloudSlash, ShieldCheck } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { fetchReview, type CollectionReview } from "../app/api";
import { routeHref } from "../app/router";
import { t } from "../i18n/t";
import { formatInteger, formatRelative } from "../lib/format";
import { Avatar, ErrorState, PageHeader, Spinner } from "../ui/primitives";

const POLL_MS = 10_000;

function monthLabel(month: string): string {
  const [year, number] = month.split("-");
  return t("{y} 年 {m} 月", { y: year, m: Number(number) });
}

export function ReviewPage() {
  const [review, setReview] = useState<CollectionReview | null>(null);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    let timer: number | undefined;
    const load = () => {
      fetchReview()
        .then((body) => {
          if (!active) return;
          if ("state" in body) {
            // First visit: the server is building it in the background.
            setBuilding(true);
            timer = window.setTimeout(load, POLL_MS);
          } else {
            setBuilding(false);
            setReview(body);
          }
        })
        .catch(() => active && setError(true));
    };
    setError(false);
    load();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [attempt]);

  if (error) return <ErrorState message={t("回顾读取失败，请检查 NAS 服务是否正常。")} onRetry={() => setAttempt((value) => value + 1)} />;
  if (!review) {
    return (
      <>
        <PageHeader title={t("收藏回顾")} />
        <div className="review-wait">
          <Spinner size={20} />
          <p>{building ? t("第一次生成要一分钟左右，好了会自动显示。") : t("正在读取…")}</p>
        </div>
      </>
    );
  }

  const { totals, vanished } = review;
  const since = totals.since ? new Date(totals.since * 1000) : null;
  const peakMonth = Math.max(1, ...review.months.map((entry) => entry.added));
  const peakYear = Math.max(1, ...review.publishedYears.map((entry) => entry.count));
  const savedShare = totals.items ? Math.round((totals.saved / totals.items) * 100) : 0;

  return (
    <div className="review">
      <PageHeader
        title={t("收藏回顾")}
        subtitle={
          since
            ? t("从 {y} 年 {m} 月开始，你一共收藏了 {n} 个作品，{s} 个已经存到 NAS（{p}%）。", {
                y: since.getFullYear(),
                m: since.getMonth() + 1,
                n: formatInteger(totals.items),
                s: formatInteger(totals.saved),
                p: savedShare,
              })
            : t("还没有收藏记录。")
        }
        actions={<span className="cap2">{t("每天更新一次 · {when}", { when: formatRelative(review.builtAt) })}</span>}
      />

      <div className="review-grid">
        <section className="card review-card review-months" aria-label={t("每月新收藏")}>
          <h2 className="h4">{t("每月新收藏")}</h2>
          <p className="cap">{t("深色是已经存到 NAS 的部分")}</p>
          <ol className="review-bars">
            {review.months.map((entry) => (
              <li key={entry.month}>
                <span className="review-bar-label">
                  {monthLabel(entry.month)}
                  {entry.month === review.firstMonth ? <em>{t("首次导入")}</em> : null}
                </span>
                <span className="review-bar-track" aria-hidden="true">
                  <span className="review-bar" style={{ width: `${(entry.added / peakMonth) * 100}%` }}>
                    <span className="review-bar-saved" style={{ width: `${entry.added ? (entry.saved / entry.added) * 100 : 0}%` }} />
                  </span>
                </span>
                <span className="review-bar-value num">{formatInteger(entry.added)}</span>
              </li>
            ))}
          </ol>
          {review.firstMonth ? <p className="cap review-note">{t("抖藏家开始工作之前的收藏，都算在首次导入的那个月。")}</p> : null}
        </section>

        <section className="card review-card review-vanished" aria-label={t("已经消失的作品")}>
          <h2 className="h4">{t("已经消失的作品")}</h2>
          <p className="cap">{t("抖音上已删除或设为私密")}</p>
          <div className="review-big num">{formatInteger(vanished.total)}</div>
          <div className="review-split">
            <span className="review-split-saved">
              <ShieldCheck size={16} weight="fill" />
              {t("幸好存下了 {n} 个", { n: formatInteger(vanished.saved) })}
            </span>
            {vanished.lost ? (
              <span className="review-split-lost">
                <CloudSlash size={16} />
                {t("没来得及存 {n} 个", { n: formatInteger(vanished.lost) })}
              </span>
            ) : null}
          </div>
          <a className="btn btn-secondary btn-sm" href={routeHref({ name: "gone", filters: {} })}>
            {t("去看看")}
          </a>
        </section>

        <section className="card review-card review-creators" aria-label={t("最爱的博主")}>
          <h2 className="h4">{t("最爱的博主")}</h2>
          <p className="cap">{t("收藏作品最多的 {n} 位", { n: review.topCreators.length })}</p>
          <ol className="review-creator-list">
            {review.topCreators.map((creator, index) => (
              <li key={creator.id}>
                <a href={routeHref({ name: "creator", creatorId: creator.id, filters: {} })}>
                  <span className="review-rank num">{index + 1}</span>
                  <Avatar src={creator.avatarUrl} name={creator.name} size={32} />
                  <span className="review-creator-name">{creator.name}</span>
                  <span className="review-creator-count num">{t("{n} 个", { n: formatInteger(creator.count) })}</span>
                  {creator.vanished ? <span className="pill down">{t("{n} 个已消失", { n: creator.vanished })}</span> : null}
                </a>
              </li>
            ))}
          </ol>
        </section>

        <section className="card review-card review-years" aria-label={t("收藏的作品发布于")}>
          <h2 className="h4">{t("收藏的作品发布于")}</h2>
          <p className="cap">{t("按作品在抖音上的发布年份")}</p>
          <ol className="review-columns">
            {review.publishedYears.map((entry) => (
              <li key={entry.year} title={t("{y} 年发布：{n} 个", { y: entry.year, n: formatInteger(entry.count) })}>
                <span className="review-column-value num">{formatInteger(entry.count)}</span>
                <span className="review-column" style={{ height: `${Math.max(3, (entry.count / peakYear) * 100)}%` }} />
                <span className="review-column-label num">{entry.year}</span>
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  );
}
