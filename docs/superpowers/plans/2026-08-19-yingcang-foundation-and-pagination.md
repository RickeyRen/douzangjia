# 影仓数据基础与连续分页实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成“影仓”品牌基础、可迁移的账户媒体库数据模型，并修复网格与沉浸视图只自动加载一次的问题。

**Architecture:** 通过只向前的 SQLite migration 在保留原有收藏表的同时增加统一来源、创作者和同步检查点，repository 提供幂等写入。前端将一次性 request-id 锁改为 cursor 级去重，每当 API 产生新游标即可继续预取，只在失败时显示重试按钮。

**Tech Stack:** Python 3.12, FastAPI, SQLite, aiosqlite, React 19, TypeScript, Vite, Vitest, Testing Library

**Spec:** `docs/superpowers/specs/2026-08-19-yingcang-account-library-design.md`, `docs/superpowers/specs/2026-08-19-yingcang-web-console-design.md`

## Global Constraints

- 产品名为“影仓”，副标题为“私人短视频媒体库”。
- 不修改 `001_initial.sql` 或 `002_download_progress.sql`；数据模型只通过新 migration 升级。
- 新表不删除或替换现有 `collections`, `collection_items`, `items` 和媒体记录。
- 新文案必须同时提供 `zh-CN` 和 `en`。
- 无限滚动的正常路径不显示“加载更多”按钮；按钮只用于请求失败后重试。
- Chromium profile、cookie、`.env`、SQLite 数据库、媒体和构建产物不得加入 Git。

---

## 文件结构

- Create `src/douyin_archive/migrations/003_library_sources.sql`: 账户来源、创作者、来源作品和同步检查点表。
- Create `src/douyin_archive/library_models.py`: 来源类型、同步状态及数据传输对象。
- Create `src/douyin_archive/library_repository.py`: 来源、创作者、关系和检查点的幂等写入与统计。
- Create `src/douyin_archive/routes/library.py`: 来源完整度与统一媒体流 API。
- Modify `src/douyin_archive/app.py`: 注册 library router。
- Modify `tests/test_database.py`: 锁定新 schema 和旧数据保留。
- Create `tests/test_library_repository.py`: 锁定幂等性、计数和检查点。
- Create `tests/test_library_api.py`: 锁定来源完整度与游标 API。
- Modify `web/src/features/feed/FeedPage.tsx`: cursor 级自动分页及失败重试。
- Modify `web/src/features/feed/FeedPage.test.tsx`: 三游标自动分页回归。
- Modify `web/src/i18n/zh-CN.ts`, `web/src/i18n/en.ts`, `web/index.html`, `README.md`: 影仓品牌与中英文案。

### Task 1: 数据库迁移与数据对象

**Files:**
- Create: `src/douyin_archive/migrations/003_library_sources.sql`
- Create: `src/douyin_archive/library_models.py`
- Modify: `tests/test_database.py`

**Interfaces:**
- Produces: `LibrarySourceKind`, `LibrarySyncStatus`, `LibrarySource`, `CreatorRecord`, `SourceIntegrity`
- Produces tables: `library_sources`, `creators`, `source_items`, `sync_checkpoints`

- [ ] **Step 1: Write the failing schema test**

```python
async def test_schema_creates_library_source_tables(database: Database) -> None:
    rows = await database.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {row["name"] for row in rows}
    assert {"library_sources", "creators", "source_items", "sync_checkpoints"} <= names
```

- [ ] **Step 2: Run test to verify RED**

Run: `pytest tests/test_database.py::test_schema_creates_library_source_tables -q`

Expected: FAIL because the four tables do not exist.

- [ ] **Step 3: Add the migration and typed models**

The migration must define `library_sources.id` as a stable text primary key; `kind` accepts `post`, `like`, `favorite_collection`, `favorite_video`, `favorite_music`, `favorite_series`, `favorite_drama`, `watch_history`, `watch_later`, `reservation`, and `following`; `sync_status` accepts `never`, `running`, `complete`, `incomplete`, and `failed`. `source_items` uses `(source_id, item_id)` as its primary key and references existing `items(remote_id)`. `sync_checkpoints` stores `source_id`, `cursor`, `page_index`, `discovered_count`, `response_digest`, `stop_reason`, and timestamps.

Define the enums as `str, Enum` and DTOs as frozen slotted dataclasses so repository and routes share exact names without ORM coupling.

- [ ] **Step 4: Run migration tests to verify GREEN**

Run: `pytest tests/test_database.py -q`

Expected: all database tests pass and the legacy table assertions remain green.

- [ ] **Step 5: Commit checkpoint**

```bash
git add src/douyin_archive/migrations/003_library_sources.sql src/douyin_archive/library_models.py tests/test_database.py
git commit -m "feat: add yingcang library source schema"
```

### Task 2: 来源与创作者 Repository

**Files:**
- Create: `src/douyin_archive/library_repository.py`
- Create: `tests/test_library_repository.py`

**Interfaces:**
- Consumes: `LibrarySource`, `CreatorRecord`, `LibrarySyncStatus`
- Produces: `LibraryRepository.upsert_source(source: LibrarySource) -> None`
- Produces: `LibraryRepository.upsert_creator(creator: CreatorRecord) -> None`
- Produces: `LibraryRepository.link_source_item(source_id: str, item_id: str, remote_order: str | None, metadata: dict[str, object] | None = None) -> None`
- Produces: `LibraryRepository.source_integrity(source_id: str) -> SourceIntegrity | None`
- Produces: `LibraryRepository.save_checkpoint(...) -> None`

- [ ] **Step 1: Write failing idempotency and integrity tests**

```python
async def test_source_item_link_is_idempotent(database: Database) -> None:
    archive = ArchiveRepository(database)
    library = LibraryRepository(database)
    await archive.upsert_item("item-1", "author", "clip", "video")
    await library.upsert_source(LibrarySource(id="likes", kind=LibrarySourceKind.LIKE, remote_id="self", name="喜欢", declared_count=2))
    await library.link_source_item("likes", "item-1", "0001")
    await library.link_source_item("likes", "item-1", "0001")
    integrity = await library.source_integrity("likes")
    assert integrity is not None
    assert integrity.discovered_count == 1
    assert integrity.declared_count == 2
    assert integrity.missing_count == 1
    assert integrity.complete is False
```

- [ ] **Step 2: Run test to verify RED**

Run: `pytest tests/test_library_repository.py -q`

Expected: FAIL because `LibraryRepository` does not exist.

- [ ] **Step 3: Implement the minimal repository**

Use SQLite `INSERT ... ON CONFLICT DO UPDATE`; preserve `first_seen_at`, update `last_seen_at`, encode source-specific metadata with sorted-key JSON, and calculate `missing_count=max(declared_count-discovered_count, 0)`. A source is complete only when `sync_status='complete'` and either `declared_count` is null or equals `discovered_count`.

- [ ] **Step 4: Verify GREEN**

Run: `pytest tests/test_library_repository.py tests/test_database.py -q`

Expected: all repository and migration tests pass.

- [ ] **Step 5: Commit checkpoint**

```bash
git add src/douyin_archive/library_repository.py tests/test_library_repository.py
git commit -m "feat: add library source repository"
```

### Task 3: 来源完整度与统一媒体流 API

**Files:**
- Create: `src/douyin_archive/routes/library.py`
- Create: `tests/test_library_api.py`
- Modify: `src/douyin_archive/app.py`

**Interfaces:**
- Consumes: `LibraryRepository.source_integrity(source_id)`
- Produces: `GET /api/library/sources`
- Produces: `GET /api/library/feed?sourceId=&creatorId=&cursor=&limit=`

- [ ] **Step 1: Write failing API tests**

```python
async def test_library_sources_expose_sync_gap(client, seeded_library) -> None:
    response = await client.get("/api/library/sources")
    assert response.status_code == 200
    source = response.json()["items"][0]
    assert source["declaredCount"] == 2
    assert source["discoveredCount"] == 1
    assert source["missingCount"] == 1
    assert source["complete"] is False

async def test_library_feed_uses_stable_cursor(client, seeded_library) -> None:
    first = (await client.get("/api/library/feed?sourceId=likes&limit=1")).json()
    second = (await client.get(f"/api/library/feed?sourceId=likes&limit=1&cursor={first['nextCursor']}")).json()
    assert first["items"][0]["awemeId"] != second["items"][0]["awemeId"]
```

- [ ] **Step 2: Run test to verify RED**

Run: `pytest tests/test_library_api.py -q`

Expected: FAIL with 404 for both routes.

- [ ] **Step 3: Implement and register the router**

Reuse `_encode_cursor`, `_decode_cursor`, and `_serialize_item` from `routes/feed.py` by moving them into focused helpers only if import cycles appear. Apply `source_items.source_id` and `items.creator_id` filters with parameterized SQL, order by `source_items.remote_order DESC, items.remote_id DESC` for source feeds and `items.published_at DESC, items.remote_id DESC` for creator feeds, and request `limit + 1` to produce the next cursor.

- [ ] **Step 4: Verify GREEN and legacy compatibility**

Run: `pytest tests/test_library_api.py tests/test_feed_api.py -q`

Expected: new and legacy feed API tests pass.

- [ ] **Step 5: Commit checkpoint**

```bash
git add src/douyin_archive/routes/library.py src/douyin_archive/routes/feed.py src/douyin_archive/app.py tests/test_library_api.py
git commit -m "feat: expose yingcang library APIs"
```

### Task 4: 三游标连续自动分页

**Files:**
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/features/feed/FeedPage.test.tsx`

**Interfaces:**
- Preserves: `fetchFeed({ collectionId, author, search, cursor })`
- Produces: one automatic request per distinct cursor; retry for the same cursor only after user action

- [ ] **Step 1: Write a failing three-cursor regression test**

Mock four pages where cursors are `cursor-2`, `cursor-3`, `cursor-4`, then `null`. Capture the `IntersectionObserver` callback and trigger the sentinel after each render. Assert the mock receives the initial request plus three requests with those distinct cursors, the UI contains all four unique items, and `screen.queryByRole("button", { name: /加载更多/i })` is null while requests succeed.

- [ ] **Step 2: Run test to verify RED**

Run: `cd web && npm test -- --run src/features/feed/FeedPage.test.tsx`

Expected: the test times out or observes only the first automatic pagination request because `autoPaginatedRequestId` never changes for a new cursor.

- [ ] **Step 3: Replace request-level locking with cursor-level deduplication**

Replace `autoPaginatedRequestId` with `autoPaginatedCursor`. Reset it when query filters change. In the observer, compare against the current `nextCursor`; immediately record that cursor before calling `loadMore`. When `loadMore` fails, clear `autoPaginatedCursor` for the failed cursor so the explicit retry can run. Render a button only when `loadMoreError` is true; render an `aria-live` loading indicator for successful background pagination.

- [ ] **Step 4: Verify GREEN**

Run: `cd web && npm test -- --run src/features/feed/FeedPage.test.tsx`

Expected: all existing feed behavior and the new three-cursor regression pass.

- [ ] **Step 5: Commit checkpoint**

```bash
git add web/src/features/feed/FeedPage.tsx web/src/features/feed/FeedPage.test.tsx
git commit -m "fix: continuously paginate archive feeds"
```

### Task 5: 影仓品牌和回归验证

**Files:**
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`
- Modify: `web/src/i18n/i18n.test.ts`
- Modify: `web/index.html`
- Modify: `README.md`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces copy: `brand="影仓"`, `brandSubtitle="私人短视频媒体库"`
- Preserves Python import package: `douyin_archive` during this compatibility phase

- [ ] **Step 1: Add failing translation assertions**

```typescript
expect(zhCN.brand).toBe("影仓");
expect(zhCN.brandSubtitle).toBe("私人短视频媒体库");
expect(en.brand).toBe("Yingcang");
expect(en.brandSubtitle).toBe("Private short-video media library");
```

- [ ] **Step 2: Run test to verify RED**

Run: `cd web && npm test -- --run src/i18n/i18n.test.ts`

Expected: FAIL because the current brand is still 留影/Liuying.

- [ ] **Step 3: Apply the product rename**

Update visible UI copy, document title, package metadata description, README title and examples. Keep the Python import path and NAS data paths compatible to avoid breaking deployment; record that internal package renaming is deferred until a dedicated import-compatibility migration.

- [ ] **Step 4: Run full verification**

Run: `pytest -q`

Expected: all backend tests pass.

Run: `cd web && npm test -- --run && npm run lint && npm run build`

Expected: all frontend tests, lint and production build pass.

Run: `git diff --check && git status --short`

Expected: no whitespace errors and only intended tracked changes before commit.

- [ ] **Step 5: Commit and tag the verified phase**

```bash
git add README.md pyproject.toml web/index.html web/src/i18n
git commit -m "feat: rename private archive to yingcang"
git tag -a checkpoint/yingcang-foundation-20260819 -m "Verified Yingcang foundation and continuous pagination"
```

