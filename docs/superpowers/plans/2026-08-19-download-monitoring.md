# Download Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build durable, real-byte download monitoring from the streaming downloader through SQLite and the jobs API to an iPhone-ready activity panel.

**Architecture:** `MediaDownloader` emits throttled immutable progress snapshots. `ArchiveJobHandler` persists those snapshots in extended `media_files` rows, while a focused monitor service merges job payloads, item metadata, collection membership, and media progress into one API snapshot. React polls that snapshot once per second only while the activity panel is open and renders queue, task, and asset details.

**Tech Stack:** Python 3.14, FastAPI, aiosqlite/SQLite, httpx/anyio, pytest, React 19, TypeScript, Vitest, Testing Library, Tailwind CSS 4.

**Spec:** `docs/superpowers/specs/2026-08-19-download-monitoring-design.md`

## Global Constraints

- Progress values must come from network bytes or an existing `.part`/object file; never simulate percentages.
- Unknown totals and stale/zero speeds must produce `null` percentage or ETA values.
- Existing archive objects, SQLite data, Chromium profile, cookies, and login state must be preserved.
- The activity panel polls once per second only while mounted.
- Mobile controls must be at least 44px and layouts must not overflow at 430×932, 393×852, or 932×430.
- All user-visible strings must exist in both Chinese and English.

---

### Task 1: Durable media progress schema and repository

**Files:**
- Create: `src/douyin_archive/migrations/002_download_progress.sql`
- Modify: `src/douyin_archive/models.py`
- Modify: `src/douyin_archive/repositories.py`
- Test: `tests/test_download_progress_repository.py`

**Interfaces:**
- Produces: `MediaProgress` with `item_id`, `asset_index`, `status`, `downloaded_bytes`, `total_bytes`, `speed_bps`, and `progress_updated_at`.
- Produces: `DownloadProgressRepository.prepare_asset(...)`, `update(...)`, and `get_for_item(...)`.

- [ ] **Step 1: Write a failing repository test**

```python
progress = DownloadProgressRepository(database)
await progress.prepare_asset(asset, downloaded_bytes=3)
await progress.update("734", 0, downloaded_bytes=5, total_bytes=10, speed_bps=2.5)
row = (await progress.get_for_item("734"))[0]
assert row.downloaded_bytes == 5
assert row.total_bytes == 10
assert row.speed_bps == 2.5
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/bin/pytest tests/test_download_progress_repository.py -q`

Expected: collection fails because `DownloadProgressRepository` does not exist.

- [ ] **Step 3: Add migration, model, and minimal repository implementation**

```sql
ALTER TABLE media_files ADD COLUMN downloaded_bytes INTEGER NOT NULL DEFAULT 0;
ALTER TABLE media_files ADD COLUMN total_bytes INTEGER;
ALTER TABLE media_files ADD COLUMN speed_bps REAL NOT NULL DEFAULT 0;
ALTER TABLE media_files ADD COLUMN progress_updated_at INTEGER;
```

`prepare_asset` upserts a `pending` media row without destroying an existing ready path; `update` changes only progress/status fields.

- [ ] **Step 4: Run focused and database tests**

Run: `.venv/bin/pytest tests/test_download_progress_repository.py tests/test_database.py tests/test_storage.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/douyin_archive/migrations/002_download_progress.sql src/douyin_archive/models.py src/douyin_archive/repositories.py tests/test_download_progress_repository.py
git commit -m "feat: persist media download progress"
```

### Task 2: Real-byte downloader snapshots and resume behavior

**Files:**
- Modify: `src/douyin_archive/downloader.py`
- Modify: `tests/test_downloader.py`

**Interfaces:**
- Produces: immutable `DownloadProgressSnapshot(downloaded_bytes, total_bytes, speed_bps, eta_seconds)`.
- Changes: `MediaDownloader.download(asset, on_progress=None)` where `on_progress` is an async callable.

- [ ] **Step 1: Add failing tests for initial, streamed, resumed, completed, and unknown-total snapshots**

```python
snapshots: list[DownloadProgressSnapshot] = []
await downloader.download(asset, on_progress=snapshots.append)
assert snapshots[-1].downloaded_bytes == 6
assert snapshots[-1].total_bytes == 6
assert snapshots[-1].eta_seconds == 0
```

Use an async collector and a zero reporting interval in tests so every deterministic chunk can be asserted.

- [ ] **Step 2: Run the downloader tests and verify RED**

Run: `.venv/bin/pytest tests/test_downloader.py -q`

Expected: tests fail because the snapshot type and callback argument do not exist.

- [ ] **Step 3: Implement snapshot emission**

Track `resume_at`, monotonic sample time, sample bytes, smoothed `speed_bps`, parsed response total, and force an initial/final callback. Retain `.part` on exceptions.

- [ ] **Step 4: Run downloader tests and verify GREEN**

Run: `.venv/bin/pytest tests/test_downloader.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/douyin_archive/downloader.py tests/test_downloader.py
git commit -m "feat: emit real download progress snapshots"
```

### Task 3: Connect handler progress to SQLite

**Files:**
- Modify: `src/douyin_archive/archive_handler.py`
- Modify: `src/douyin_archive/runtime.py`
- Modify: `tests/test_archive_handler.py`

**Interfaces:**
- Consumes: `DownloadProgressRepository` and `DownloadProgressSnapshot`.
- Produces: persisted `pending → running → ready` asset lifecycle with part-size resume.

- [ ] **Step 1: Add a failing handler persistence test**

```python
rows = await DownloadProgressRepository(database).get_for_item("734")
assert rows[0].status == "ready"
assert rows[0].downloaded_bytes == len(b"original-media")
assert rows[0].total_bytes == len(b"original-media")
```

Add a second test that starts with a three-byte `.part` and asserts the first persisted running snapshot is at least three bytes.

- [ ] **Step 2: Run the handler tests and verify RED**

Run: `.venv/bin/pytest tests/test_archive_handler.py -q`

- [ ] **Step 3: Wire repository callbacks through the handler**

Prepare all payload assets, derive each canonical filename with `asset_filename`, pass an async callback to the downloader, and finalize the existing `media_files` row instead of inserting a separate row.

- [ ] **Step 4: Run handler, worker, scheduler, and storage tests**

Run: `.venv/bin/pytest tests/test_archive_handler.py tests/test_worker.py tests/test_scheduler.py tests/test_storage.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/douyin_archive/archive_handler.py src/douyin_archive/runtime.py tests/test_archive_handler.py
git commit -m "feat: persist archive worker progress"
```

### Task 4: Aggregate queue, task, asset, collection, retry, and failure details

**Files:**
- Create: `src/douyin_archive/download_monitor.py`
- Modify: `src/douyin_archive/routes/jobs.py`
- Create: `tests/test_download_monitor.py`
- Modify: `tests/test_jobs_routes.py`

**Interfaces:**
- Produces: `DownloadMonitor.snapshot(limit: int) -> dict[str, object]`.
- Changes: `GET /api/jobs` response from `{items}` to `{summary, items}` while preserving all existing item fields.

- [ ] **Step 1: Add failing monitor tests**

```python
snapshot = await DownloadMonitor(database).snapshot(limit=50)
assert snapshot["summary"]["retry"] == 1
assert snapshot["items"][0]["collections"] == ["想去的地方"]
assert snapshot["items"][0]["assets"][0]["downloadedBytes"] == 3
assert snapshot["items"][0]["errorCode"] == "MEDIA_HTTP_ERROR"
```

Cover ready-row `byte_size` fallback, unknown totals, summed running speed, ETA, status ordering, and next retry time.

- [ ] **Step 2: Run monitor and route tests and verify RED**

Run: `.venv/bin/pytest tests/test_download_monitor.py tests/test_jobs_routes.py -q`

- [ ] **Step 3: Implement the service and route delegation**

Bulk-load jobs, items, collection names, and media rows; merge payload assets by `(remote_id, asset_index)`; derive filenames with `asset_filename`; calculate aggregates only from unfinished jobs.

- [ ] **Step 4: Run monitor and API security tests**

Run: `.venv/bin/pytest tests/test_download_monitor.py tests/test_jobs_routes.py tests/test_authz_routes.py -q`

- [ ] **Step 5: Commit**

```bash
git add src/douyin_archive/download_monitor.py src/douyin_archive/routes/jobs.py tests/test_download_monitor.py tests/test_jobs_routes.py
git commit -m "feat: expose detailed download monitoring"
```

### Task 5: Render complete iPhone download monitoring

**Files:**
- Modify: `web/src/app/api.ts`
- Create: `web/src/features/status/DownloadMonitor.tsx`
- Create: `web/src/features/status/downloadFormat.ts`
- Modify: `web/src/features/status/ArchiveStatusPanel.tsx`
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/features/status/ArchiveStatusPanel.test.tsx`
- Create: `web/src/features/status/downloadFormat.test.ts`

**Interfaces:**
- Consumes: `DownloadSnapshot`, `DownloadSummary`, `DownloadJob`, and `DownloadAsset` from `api.ts`.
- Produces: `DownloadMonitor({snapshot})`, `formatBytes`, `formatSpeed`, `formatEta`, and `formatDateTime`.

- [ ] **Step 1: Add failing formatting and component tests**

```tsx
expect(screen.getByText("14.7 MB / 47.7 MB")).toBeVisible();
expect(screen.getByText("1.2 MB/s")).toBeVisible();
expect(screen.getByText("约 28 秒")).toBeVisible();
await user.click(screen.getByRole("button", { name: /海边日落/ }));
expect(screen.getByText("想去的地方")).toBeVisible();
expect(screen.getByText("000.mp4")).toBeVisible();
```

Also assert indeterminate progress, localized error text, retry countdown, `aria-expanded`, and a one-second refresh that stops after unmount.

- [ ] **Step 2: Run focused frontend tests and verify RED**

Run: `npm test -- --run web/src/features/status/downloadFormat.test.ts web/src/features/status/ArchiveStatusPanel.test.tsx`

- [ ] **Step 3: Implement the API types, formatters, monitor, and translations**

Use native `<progress>` for known totals and an animated CSS bar with `role="progressbar"` and no `aria-valuenow` for unknown totals. Keep each task summary button at least 44px and use `aria-expanded`/`aria-controls` for details.

- [ ] **Step 4: Run status and feed tests**

Run: `npm test -- --run web/src/features/status web/src/features/feed/FeedPage.test.tsx`

- [ ] **Step 5: Commit**

```bash
git add web/src/app/api.ts web/src/features/status web/src/i18n web/src/styles/app.css web/src/features/feed/FeedPage.test.tsx
git commit -m "feat: add iphone download monitor"
```

### Task 6: Full verification, responsive QA, NAS deployment, and recovery checkpoint

**Files:**
- Modify only if verification finds a tested defect in files from Tasks 1-5.

**Interfaces:**
- Consumes: complete backend and frontend implementation.
- Produces: verified NAS image and a recoverable git checkpoint/tag.

- [ ] **Step 1: Run the complete local verification suite**

Run: `.venv/bin/pytest -q`

Run: `cd web && npm test -- --run && npm run lint && npm run build`

- [ ] **Step 2: Render mobile portrait, compact portrait, landscape, and desktop**

Verify 430×932, 393×852, 932×430, and 1440×1000. For each mobile viewport assert `scrollWidth === innerWidth`, queue summary is visible, a task can expand, all progress controls remain above the bottom navigation, and the console has no errors.

- [ ] **Step 3: Create a pre-deploy checkpoint**

```bash
git status --short
git add docs/superpowers/specs/2026-08-19-download-monitoring-design.md docs/superpowers/plans/2026-08-19-download-monitoring.md src tests web
git commit -m "feat: complete real-time download monitoring"
```

- [ ] **Step 4: Deploy without copying secrets or archive state**

Use rsync exclusions for `.env`, `archive-data`, `.venv`, `node_modules`, `dist`, `.git`, Chromium profiles, SQLite databases, cookies, cache, and temporary files. Rebuild and recreate only `douyin-nas-archive`, preserving `/vol3/1000/抖音留影`.

- [ ] **Step 5: Verify production behavior with real data**

Confirm `/health/ready` reports archive root and browser profile `ok`, `/api/status` reports `douyinAuthenticated: true`, and the activity page shows the existing retry task plus its real `.part` byte count. Observe a natural retry or intended sync/download and capture authoritative evidence that persisted bytes grow, speed becomes positive, ETA appears when total is known, and final/retry state matches the database.

- [ ] **Step 6: Create final checkpoint tag and push only to an approved private GitLab remote**

```bash
git tag -a checkpoint/download-monitoring-20260819 -m "Verified NAS download monitoring"
git remote -v
```

If and only if an approved private GitLab remote exists, push the current branch and the new tag without force. Otherwise keep the branch and tag locally and report that no remote was configured.
