# 影仓账户媒体库与完整同步设计

## 目标

用统一的“来源”模型表示已登录账户的作品、喜欢、收藏夹、关注、观看历史、稍后再看和预约，并为每个来源记录远端声称数、发现数、入库数和已归档数。

## 数据模型

- `library_sources`：`id`, `kind`, `remote_id`, `name`, `declared_count`, `sync_cursor`, `sync_status`, `last_full_scan_at`, `last_incremental_scan_at`, `error_code`。
- `creators`：稳定远程 ID、昵称、抖音号、头像 URL、粉丝/作品统计、最后见到时间。
- `items`：保留原有主键，新增 `creator_id`, `cover_url`, `duration_ms`, `statistics_json`, `visibility`, `source_url`。
- `source_items`：来源与作品的多对多关系，包含远程排序键、首次/最后发现时间与来源特有元数据。
- `sync_checkpoints`：每页游标、页码、累计发现数、响应摘要和结束原因，用于中断续扫。

`collections` 与 `collection_items` 通过数据迁移转化为 `library_sources(kind='favorite_collection')` 与 `source_items`，保留现有数据和 API 兼容视图。

## Provider 契约

Provider 以能力而不是单一收藏端点建模：

- `list_sources() -> tuple[RemoteSource, ...]`
- `iter_source_pages(source: RemoteSource, cursor: str | None) -> AsyncIterator[RemotePage]`
- `get_creator(creator_id: str) -> RemoteCreator`
- `iter_creator_pages(creator_id: str, cursor: str | None) -> AsyncIterator[RemotePage]`

每页都返回 `next_cursor`, `has_more`, `declared_count` 和远程排序键。端点结构变化时记录可诊断的错误码，不记录 cookie 或完整响应体。

## 同步策略

- **首次全量扫描**：直到 `has_more=false`，不因连续旧项提前终止。
- **增量扫描**：从首页开始，只有在“已遇到最近一次完整扫描的高水位且远端声称数与本地可对账”时才可提前停止。
- **完整性修复**：数量不匹配、游标循环、空页且 `has_more=true` 或重复率异常时，标记来源为 `incomplete` 并提供强制全量重扫描。
- **并发与限速**：同一 profile 只有一个页面抓取协调器，来源串行或低并发，支持指数退避和 `Retry-After`。

## API

- `GET /api/library/sources`：来源列表与完整度。
- `GET /api/library/feed?sourceId=&creatorId=&cursor=&limit=`：统一游标流。
- `POST /api/library/sources/{id}/sync`：增量或强制全量同步。
- `GET /api/creators` 与 `GET /api/creators/{id}`：创作者列表及其本地作品。
- 现有 `/api/collections` 和 `/api/feed` 在过渡期保持兼容。

## 验收

- 迁移后原有收藏夹和作品数不减少。
- 可从中断的游标继续，不产生重复关系。
- 已知大收藏夹的远端声称数与发现数完成对账；未对账时 UI 不显示“完成”。
- 任一来源中连续请求三个不同游标均能返回去重后的稳定顺序。

