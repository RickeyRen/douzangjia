# 留影实时下载监控设计

## 背景与目标

当前下载任务仅持久化 `pending`、`running`、`completed`、`retry` 和 `failed` 等状态。下载器虽然以流式方式写入 `.part` 文件，但没有把已下载字节、响应总长度、速度或当前媒体文件写回数据库；`/api/jobs` 也只返回任务状态、重试次数和错误代码。因此活动页无法显示真实进度条或下载详情。

本次改动要建立一条完整的、可恢复的数据链路：下载器采样真实字节进度，SQLite 持久化每个媒体文件的快照，API 聚合任务与全局队列状态，手机端活动页以一秒间隔展示这些数据。NAS 或浏览器重启后必须从数据库和现有 `.part` 文件恢复，而不是从零开始或显示模拟进度。

## 范围

交付内容包括：

- 单媒体文件的文件名、媒体类型、状态、已下载字节、总字节、百分比、速度、预计剩余时间和更新时间。
- 单作品任务的作者、描述、收藏夹、媒体数量、当前媒体、聚合字节进度、速度、预计剩余时间、重试次数、下次重试时间和失败原因。
- 全局队列的运行、等待、重试、失败、完成数量，以及所有未完成任务的聚合字节进度、速度和预计剩余时间。
- iPhone 15 Pro Max 竖屏和横屏下可触控、可展开的活动页。
- 中英文状态、错误和单位文案。
- 后端与前端自动化测试、生产构建、NAS 部署和真实下载验证。

暂停、取消、删除、调整任务优先级和修改抖音账户内容不在本次范围内。未知总大小的响应必须显示不确定进度，不得虚构百分比或剩余时间。

## 方案选择

采用“SQLite 持久快照 + 活动页一秒轮询”。SSE 或 WebSocket 虽然可以减少可见延迟，但需要维护连接、广播和重连状态；进度仍然必须持久化才能跨 NAS 重启恢复。单机 NAS 最多两个下载 worker，每秒读取一次轻量聚合快照更简单、可靠，并且在活动面板关闭时不会产生请求。

下载器每个网络 chunk 都更新内存计数，但最多每 500ms 持久化一次中间快照，并在开始、完成和错误前强制写入。这样 UI 延迟不超过约 1.5 秒，同时避免每个 chunk 都写 SQLite。

## 数据模型

新增迁移 `002_download_progress.sql`，给 `media_files` 增加：

- `downloaded_bytes INTEGER NOT NULL DEFAULT 0`
- `total_bytes INTEGER`
- `speed_bps REAL NOT NULL DEFAULT 0`
- `progress_updated_at INTEGER`

`media_files.status` 继续作为单文件状态，使用 `pending`、`running` 和 `ready`。任务发生可重试或终止错误时，API 用 `download_jobs.status` 和 `last_error_code` 覆盖当前未完成媒体的展示状态，避免在 handler 与 worker 之间重复维护两套错误分类。

历史 `ready` 媒体使用 `byte_size` 作为已下载与总字节的回退值，因此迁移后旧归档立即能显示完整大小。待处理任务的资产清单继续从 `download_jobs.payload_json` 读取；handler 开始时为每个资产 upsert 一行 `media_files`，并从现有 `.part` 文件大小恢复 `downloaded_bytes`。

## 下载器与持久化流程

`MediaDownloader.download` 接受可选异步进度回调。回调快照包含 `downloaded_bytes`、`total_bytes`、`speed_bps` 和 `eta_seconds`：

1. 检查完整对象；若已存在，发出一次完成快照并直接返回。
2. 检查 `.part` 文件并把它的大小作为初始已下载字节。
3. 从 `expected_size`、`Content-Range` 或 `Content-Length` 解析总大小。
4. 下载过程中按单调时钟计算窗口速度；总大小已知且速度大于零时计算 ETA。
5. 每 500ms 或结束时回调一次；异常传播前保留最后一个 `.part` 和持久快照。

`ArchiveJobHandler` 负责把进度回调写入 `media_files`，下载完成后写入相对路径、校验值、真实大小并将状态改为 `ready`。断点续传时页面先显示 `.part` 的已有大小，再继续增长。

## API 契约

`GET /api/jobs?limit=50` 保留现有字段并增加：

```json
{
  "summary": {
    "pending": 2,
    "running": 1,
    "retry": 1,
    "failed": 0,
    "completed": 1569,
    "downloadedBytes": 15429894,
    "totalBytes": 50000000,
    "speedBps": 1240000,
    "etaSeconds": 28
  },
  "items": [
    {
      "id": 708,
      "remoteId": "…",
      "author": "作者",
      "description": "作品描述",
      "collections": ["想去的地方"],
      "status": "retry",
      "attempts": 8,
      "nextAttemptAt": 1787095502,
      "errorCode": "MEDIA_HTTP_ERROR",
      "downloadedBytes": 15429894,
      "totalBytes": 50000000,
      "speedBps": 0,
      "etaSeconds": null,
      "assets": [
        {
          "index": 0,
          "fileName": "000.mp4",
          "mediaType": "video",
          "status": "retry",
          "downloadedBytes": 15429894,
          "totalBytes": 50000000,
          "speedBps": 0,
          "etaSeconds": null,
          "updatedAt": 1787095502
        }
      ]
    }
  ]
}
```

全局字节进度只聚合未完成任务，避免大量历史完成记录让当前队列永远接近 100%。`totalBytes` 只在所有参与聚合的文件总大小都已知时返回数值，否则为 `null`；ETA 同理。速度只汇总 `running` 资产。

## 手机端体验

活动页“下载”标签顶部显示队列概览：总进度、已下载/总字节、总速度和剩余时间，下方显示五种状态数量。任务列表优先排序为运行、等待、重试、失败、完成。

每张任务卡的摘要行显示作品描述、状态徽标和进度条；运行任务显示速度与 ETA，重试任务显示失败原因和下次重试倒计时。点击卡片展开后显示作者、收藏夹、尝试次数、更新时间，以及每个媒体文件的文件名、类型、字节进度、速度和状态。

所有展开控件至少 44px，可通过键盘操作并提供 `aria-expanded`。430×932 和 393×852 竖屏保持单列；932×430 横屏允许摘要指标两列排列，但不产生横向滚动。活动面板打开时每秒刷新，关闭后立即停止定时器。

## 错误与边界

- `MEDIA_HTTP_ERROR`、`MEDIA_GONE`、`RATE_LIMITED`、`DOWNLOAD_FAILED`、`FILESYSTEM_ERROR`、`STORAGE_FULL` 和 `WORKER_RESTARTED` 映射为可读中文/英文说明，同时保留原错误码。
- 未知总大小显示“总大小未知”和不确定进度条。
- 速度为零或快照陈旧时不显示虚假 ETA。
- API 聚合失败时保留上一次成功画面并显示非阻塞错误，不把任务列表清空。
- 已完成历史任务没有新进度列时，以 `media_files.byte_size` 回填展示。

## 验证标准

- 单元测试证明初始、断点、流式、完成和未知总大小快照都来自真实字节数。
- repository/handler 测试证明进度跨数据库重开保留，完成后状态和大小正确。
- API 测试覆盖全局聚合、收藏夹、资产详情、重试和历史回退。
- React 测试覆盖总览、确定/不确定进度、展开详情、错误文案、重试倒计时及一秒刷新/卸载停止。
- 全量 `pytest`、前端测试、lint 和生产构建通过。
- iPhone 15 Pro Max 竖屏与横屏渲染无横向溢出、无控制台错误，进度详情可触达。
- NAS 容器健康，持久抖音会话未丢失；真实 `.part` 或新下载的字节增长能在网页中看到，并在完成或重试后显示一致状态。
