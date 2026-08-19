# 影仓归档批次与创作者追更实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为单作品、来源和创作者提供幂等、持久化、可观察的归档批次，并支持创作者自动追更。

**Architecture:** 通过只向前的 SQLite migration 新增 `archive_batches`、`archive_batch_items`、`creator_subscriptions` 和 `job_events`。Repository 将用户操作展开为现有的幂等 `download_jobs`，保留已完成媒体并聚合实时进度。路由仅接受稳定来源、作品和创作者 ID。

**Tech Stack:** Python 3.13, FastAPI, SQLite, React 19, TypeScript, Vitest

**Spec:** `docs/superpowers/specs/2026-08-19-yingcang-archive-jobs-design.md`

## 全局约束

- 取消或删除远端关系永不删除已归档媒体。
- 重复点击不产生重复媒体或并发下载。
- 已完成的 `download_jobs` 不因同步或批次展开被重新入队。
- 所有写 API 继续使用现有管理会话与 CSRF 保护。
- 中英文界面文案同步提供。

## Task 1: 数据库与 Repository

**Files:**
- Create: `src/douyin_archive/migrations/004_archive_batches.sql`
- Create: `src/douyin_archive/archive_repository.py`
- Modify: `tests/test_database.py`
- Create: `tests/test_archive_repository.py`

- [ ] 先写 migration 和幂等批次创建失败测试。
- [ ] 实现 batch、batch item、subscription 与 event 的持久化。
- [ ] 验证重复单作品/来源请求只复用未结束批次。

## Task 2: 归档展开服务

**Files:**
- Create: `src/douyin_archive/archive_service.py`
- Modify: `src/douyin_archive/repositories.py`
- Create: `tests/test_archive_service.py`

- [ ] 先写单作品、来源、创作者批次测试。
- [ ] 从 `items` / `source_items` 展开任务，只入队未完成作品。
- [ ] 聚合子任务数量、字节、速度和错误状态。

## Task 3: HTTP API 与调度

**Files:**
- Create: `src/douyin_archive/routes/archive.py`
- Modify: `src/douyin_archive/api.py`
- Modify: `src/douyin_archive/runtime.py`
- Modify: `src/douyin_archive/scheduler.py`
- Create: `tests/test_archive_routes.py`

- [ ] 先写各写 API 的 202、404、幂等和 CSRF 测试。
- [ ] 实现单作品、来源、创作者、批次列表/详情及暂停/继续/取消。
- [ ] 创作者订阅默认关闭；启用后由调度器检查到期项。

## Task 4: 前端操作与进度

**Files:**
- Modify: `web/src/app/api.ts`
- Modify: `web/src/features/feed/FeedCard.tsx`
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/features/status/ArchiveStatusPanel.tsx`
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`
- Add/modify related Vitest tests.

- [ ] 单作品、当前来源、创作者页面均提供明确归档操作。
- [ ] 创作者页面可切换自动追更。
- [ ] 活动面板显示批次整体进度、子任务和稳定错误码。

## Task 5: 验收与发布

- [ ] 运行 Python 全量测试、Ruff、Vitest、ESLint、Vite build 和 `docker compose config`。
- [ ] 在 Chrome 桌面和 430 x 932 视口验收主要操作。
- [ ] 创建 checkpoint commit 后安全部署 NAS，验证容器健康、批次、任务恢复和媒体 Range。
- [ ] 仅在已配置用户批准的私有 GitLab 远程时推送当前分支和新标签。
