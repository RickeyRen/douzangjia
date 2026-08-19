# 影仓归档任务与创作者追更设计

## 目标

为单作品、整个来源和创作者全部作品提供统一、持久化、可观察的归档任务，并支持创作者自动追更。

## 任务模型

- `archive_batches`：一次用户操作或定时任务，包含 `kind`, `target_id`, `status`, `discovered_count`, `completed_count`, `failed_count`, `total_bytes`, `downloaded_bytes`。
- `download_jobs`：继续表示单作品的媒体下载，新增 `batch_id`, `priority`, `paused_at`, `cancel_requested_at`。
- `creator_subscriptions`：`creator_id`, `enabled`, `scan_interval_seconds`, `last_scan_at`, `next_scan_at`, `archive_new_items`。
- `job_events`：任务状态事件、错误码和少量脱敏上下文，用于详情和诊断。

## 任务行为

- **单作品**：立即建立或复用幂等下载任务。
- **来源批量**：先扫描来源并产生 batch，再按优先级展开子任务；同一作品不重复下载。
- **创作者全部作品**：先完整扫描创作者作品流，在可见边界内全部入库后展开下载。
- **自动追更**：调度器到期扫描订阅创作者，只为新项建立下载任务。
- **控制**：batch 可暂停、恢复和取消未开始的子任务；已写入的完整媒体不因取消被删除。

## 存储语义

- 文件目录使用稳定的创作者 ID 和作品 ID；用户可读的昵称只用于显示与可选别名，避免改名导致文件移动。
- 下载写入临时文件，校验字节数与可用时的摘要后原子更名。
- 媒体库记录实际相对路径；不从昵称推导真实路径。
- 删除远端收藏关系不删除本地文件，符合“永久保留”。

## API

- `POST /api/archive/items/{id}`
- `POST /api/archive/sources/{id}`
- `POST /api/archive/creators/{id}`
- `PUT /api/creator-subscriptions/{creatorId}`
- `GET /api/archive/batches` 与 `GET /api/archive/batches/{id}`
- `POST /api/archive/batches/{id}/{pause|resume|cancel}`

所有写操作都返回 `202` 和 batch/job ID，前端通过实时事件流或短周期查询更新。

## 验收

- 重复点击单作品下载不产生重复文件或并发任务。
- 一个包含至少两页作品的创作者 batch 能完成发现、下载和进度汇总。
- 重启容器后待执行、暂停和重试任务状态不丢失。
- 订阅创作者出现新作品时只新增必要的子任务。

