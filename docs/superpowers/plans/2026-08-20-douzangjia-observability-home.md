# DouZangJia Observability Home Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real home page with persistent observability, per-category download control, account health, rich video/file details, and truthful remote availability.

**Architecture:** Extend SQLite with download policies/intents, account identity, telemetry, availability, and media-probe fields. Keep discovery metadata-first, gate automatic jobs through a policy service, expose snapshots/history/events through focused API modules, and render a responsive dark-first React home using accessible SVG charts.

**Tech Stack:** Python 3.12, FastAPI, aiosqlite, APScheduler, React, TypeScript, Vite, Vitest, CSS, native SVG, Server-Sent Events.

**Spec:** `docs/superpowers/specs/2026-08-20-douzangjia-observability-home-design.md`

## Global Constraints

- Existing downloaded files, SQLite rows, Chromium profile, cookies, and collection projections must never be deleted by migration or policy changes.
- Existing installations default favorite collections to auto-download and all other account sources to metadata-only.
- A cookie row alone is not proof of a healthy Douyin login.
- `deleted` requires explicit remote evidence; authentication, rate limit, and network failures remain distinct states.
- Unknown remote totals and unknown byte totals never produce a fabricated 100% progress value.
- New UI copy must exist in both `zh-CN` and `en` dictionaries.
- Dashboard real-time updates use event push with snapshot recovery, not whole-page polling.

---

### Task 1: Durable policy, identity, telemetry, availability, and media schema

**Files:**
- Create: `src/douyin_archive/migrations/007_observability_home.sql`
- Test: `tests/test_observability_migration.py`

**Interfaces:**
- Produces tables `download_intents`, `douyin_account`, `metric_samples`, `remote_checks`.
- Produces `library_sources.auto_download_enabled`, `library_sources.download_policy_updated_at`.
- Produces technical columns on `media_files` for probe results.

- [ ] **Step 1: Write a migration test** that opens a legacy database, applies migrations, and asserts favorite collections are enabled while `post`, `like`, and `watch_history` remain disabled.
- [ ] **Step 2: Run** `pytest tests/test_observability_migration.py -v` and verify it fails because migration 007 is absent.
- [ ] **Step 3: Add migration 007** with check-constrained status columns, foreign keys, retention indexes, and an `UPDATE library_sources SET auto_download_enabled=1 WHERE kind='favorite_collection'` migration default.
- [ ] **Step 4: Run** `pytest tests/test_observability_migration.py -v` and verify all migration/default assertions pass.
- [ ] **Step 5: Commit** `feat: add observability and download policy schema`.

### Task 2: Download policy service and shared intents

**Files:**
- Create: `src/douyin_archive/download_policy.py`
- Modify: `src/douyin_archive/repositories.py`
- Modify: `src/douyin_archive/archive_service.py`
- Test: `tests/test_download_policy.py`

**Interfaces:**
- Produces `DownloadPolicyService.list_sources() -> list[DownloadSourcePolicy]`.
- Produces `set_enabled(source_id: str, enabled: bool) -> DownloadSourcePolicy`.
- Produces `record_intent(item_id: str, origin_type: str, origin_id: str, payload: dict) -> DownloadJob`.
- Produces `remove_source_intents(source_id: str) -> int`; it pauses only unclaimed jobs with no remaining active intent.

- [ ] **Step 1: Write failing tests** for favorite defaults, enabling source backfill, shared-source disable, manual intent priority, and completed-file preservation.
- [ ] **Step 2: Run** `pytest tests/test_download_policy.py -v` and verify missing service failures.
- [ ] **Step 3: Implement focused dataclasses and repository methods** using transactions so intent creation and job creation are atomic.
- [ ] **Step 4: Route manual item/source archive calls through a `manual` intent** without changing public endpoints.
- [ ] **Step 5: Run** `pytest tests/test_download_policy.py tests/test_archive_service.py -v`.
- [ ] **Step 6: Commit** `feat: add source download policies and shared intents`.

### Task 3: Apply category policies during sync

**Files:**
- Modify: `src/douyin_archive/sync_service.py`
- Modify: `src/douyin_archive/runtime.py`
- Test: `tests/test_sync_download_policy.py`
- Test: `tests/test_sync_service.py`

**Interfaces:**
- Consumes `DownloadPolicyService.record_source_discovery(source_id, item)`.
- Produces metadata for every discovered source while creating jobs only for enabled sources.

- [ ] **Step 1: Write failing tests** proving disabled collections persist `source_items` without jobs, enabled account sources create jobs, and shared items keep one job.
- [ ] **Step 2: Run** `pytest tests/test_sync_download_policy.py -v` and verify current unconditional collection enqueue fails the assertions.
- [ ] **Step 3: Inject the policy service into `SyncService`** and replace direct `enqueue_unique` calls with policy-aware discovery.
- [ ] **Step 4: Preserve creator subscription behavior** by recording `creator` intents at its existing enqueue point.
- [ ] **Step 5: Run** `pytest tests/test_sync_download_policy.py tests/test_sync_service.py tests/test_creator_sync.py -v`.
- [ ] **Step 6: Commit** `feat: honor category download policies during discovery`.

### Task 4: Account identity and truthful health state

**Files:**
- Create: `src/douyin_archive/account_health.py`
- Modify: `src/douyin_archive/provider/douyin.py`
- Modify: `src/douyin_archive/runtime.py`
- Modify: `src/douyin_archive/api.py`
- Test: `tests/test_account_health.py`

**Interfaces:**
- Produces `AccountHealthService.snapshot() -> dict[str, object]`.
- Produces `record_success(profile: DouyinAccountProfile, verified_at: int)` and `record_failure(code: str, checked_at: int)`.
- `/api/status` adds `douyinAccount` and `douyinHealth` without exposing cookies or signed URLs.

- [ ] **Step 1: Write failing state-machine tests** for healthy, degraded, expired, rate-limited, and unknown states plus identity rename updates.
- [ ] **Step 2: Run** `pytest tests/test_account_health.py -v`.
- [ ] **Step 3: Normalize the logged-in self profile** from a real profile/API response into stable ID, nickname, unique ID, and avatar.
- [ ] **Step 4: Record successful real verification around serialized sync startup**; map session expiry, verification challenge, provider change, and network failure separately.
- [ ] **Step 5: Extend `/api/status` and confirm serialized output contains no secret fields.**
- [ ] **Step 6: Run** `pytest tests/test_account_health.py tests/test_runtime.py tests/test_auth_routes.py -v`.
- [ ] **Step 7: Commit** `feat: expose Douyin account identity and health`.

### Task 5: Persistent dashboard metrics and source aggregates

**Files:**
- Create: `src/douyin_archive/telemetry.py`
- Create: `src/douyin_archive/dashboard_service.py`
- Modify: `src/douyin_archive/runtime.py`
- Modify: `src/douyin_archive/routes/dashboard.py`
- Modify: `src/douyin_archive/routes/library.py`
- Test: `tests/test_dashboard_service.py`

**Interfaces:**
- Produces `TelemetrySampler.sample()`, `prune()`, and `series(window: str)`.
- Produces `DashboardService.snapshot()`, `series(window)`, and `source_progress()`.
- `source_progress()` returns discovered, archived, pending, running, retry, failed, archivedBytes, knownTotalBytes, and countPercent.

- [ ] **Step 1: Write failing aggregate tests** with one item shared across two sources and assert global physical bytes are deduplicated while per-source logical bytes are explicit.
- [ ] **Step 2: Write failing history tests** for 15-minute and 24-hour buckets and empty-history behavior.
- [ ] **Step 3: Run** `pytest tests/test_dashboard_service.py -v`.
- [ ] **Step 4: Implement the sampler** as a failure-isolated runtime task every 5 seconds; retain raw rows 24 hours and compact old data without blocking workers.
- [ ] **Step 5: Refactor `/api/dashboard` through `DashboardService` and add `/api/dashboard/series?window=15m|24h|7d`.**
- [ ] **Step 6: Extend source serialization with policy and progress fields.**
- [ ] **Step 7: Run** `pytest tests/test_dashboard_service.py tests/test_library_api.py tests/test_download_monitor.py -v`.
- [ ] **Step 8: Commit** `feat: add persistent dashboard telemetry and source progress`.

### Task 6: Event stream for live dashboard updates

**Files:**
- Create: `src/douyin_archive/dashboard_events.py`
- Modify: `src/douyin_archive/routes/dashboard.py`
- Modify: `src/douyin_archive/runtime.py`
- Test: `tests/test_dashboard_events.py`

**Interfaces:**
- Produces `DashboardEventBus.publish(event_type: str, data: dict)` and `subscribe()`.
- Produces `GET /api/events` SSE frames with `snapshot`, `download`, `health`, and keepalive events.

- [ ] **Step 1: Write failing tests** for initial snapshot, ordered events, disconnect cleanup, and no secret keys.
- [ ] **Step 2: Run** `pytest tests/test_dashboard_events.py -v`.
- [ ] **Step 3: Implement bounded subscriber queues** so a slow browser receives a fresh snapshot rather than growing memory.
- [ ] **Step 4: Publish telemetry and queue changes**; add SSE response with reconnect retry and periodic keepalive.
- [ ] **Step 5: Run** `pytest tests/test_dashboard_events.py tests/test_dashboard_service.py -v`.
- [ ] **Step 6: Commit** `feat: stream live dashboard events`.

### Task 7: Rich item metadata, local file probe, and remote availability

**Files:**
- Modify: `src/douyin_archive/models.py`
- Modify: `src/douyin_archive/provider/normalizers.py`
- Modify: `src/douyin_archive/repositories.py`
- Create: `src/douyin_archive/media_probe.py`
- Create: `src/douyin_archive/remote_availability.py`
- Modify: `src/douyin_archive/routes/feed.py`
- Test: `tests/test_rich_item_detail.py`
- Test: `tests/test_remote_availability.py`

**Interfaces:**
- `RemoteItem` adds cover URL, duration, statistics, source URL, hashtags/music metadata, and remote status evidence.
- `MediaProbe.probe(path: Path) -> MediaTechnicalInfo | None` returns width, height, codec, fps, bitrate, duration.
- Item detail returns `creator`, `douyin`, `local.assets`, and `remoteAvailability` sections.

- [ ] **Step 1: Write failing normalizer tests** using a realistic fixture with creator identity, counters, duration, cover, source URL, hashtags, and music.
- [ ] **Step 2: Write failing remote-state tests** proving timeouts/auth/rate-limit never map to deleted and explicit not-found does.
- [ ] **Step 3: Run** `pytest tests/test_rich_item_detail.py tests/test_remote_availability.py -v`.
- [ ] **Step 4: Persist normalized fields** while preserving old values when a partial API response omits them.
- [ ] **Step 5: Run `ffprobe` with a timeout after completed downloads** and persist best-effort technical fields; absence of ffprobe returns `None`.
- [ ] **Step 6: Add low-priority availability checks** for stale items and an authenticated `POST /api/items/{id}/remote-check` action.
- [ ] **Step 7: Serialize checksums and safe relative paths but exclude signed URLs, cookies, and browser paths.**
- [ ] **Step 8: Run** `pytest tests/test_rich_item_detail.py tests/test_remote_availability.py tests/test_feed_api.py tests/test_downloader.py -v`.
- [ ] **Step 9: Commit** `feat: expose rich media details and remote availability`.

### Task 8: Full-page React home and accessible charts

**Files:**
- Create: `web/src/features/home/HomePage.tsx`
- Create: `web/src/features/home/HomePage.test.tsx`
- Create: `web/src/features/home/MetricCard.tsx`
- Create: `web/src/features/home/TrendChart.tsx`
- Create: `web/src/features/home/StorageDonut.tsx`
- Create: `web/src/features/home/SourceProgressTable.tsx`
- Create: `web/src/features/home/useDashboardStream.ts`
- Modify: `web/src/app/api.ts`
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/features/navigation/CollectionRail.tsx`
- Modify: `web/src/features/navigation/MobileNavigation.tsx`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`

**Interfaces:**
- Produces `HomePage` as the authenticated default route/state.
- `useDashboardStream` consumes snapshot/history APIs and SSE events with reconnect.
- Charts accept typed series and render SVG plus textual summaries.

- [ ] **Step 1: Write failing component tests** for default home navigation, account health, storage values, chart empty state, source progress, and mobile labels.
- [ ] **Step 2: Run** `npm test -- --run web/src/features/home/HomePage.test.tsx` from `web`.
- [ ] **Step 3: Add typed dashboard/account/source/series API models and request functions.**
- [ ] **Step 4: Implement the 12-column dark-first home** with grouped Remnawave-inspired density and DouZangJia-specific media charts.
- [ ] **Step 5: Implement native SVG trend and donut charts** with hover/focus values, reduced-motion handling, and no new chart dependency.
- [ ] **Step 6: Implement category toggles** with optimistic UI rollback on API error and explicit metadata-only labels.
- [ ] **Step 7: Add responsive rules** for laptop widths and iPhone 15 Pro Max single-column layout.
- [ ] **Step 8: Add complete Chinese/English strings and run** `npm test && npm run build && npm run lint`.
- [ ] **Step 9: Commit** `feat: add full observability home and category progress`.

### Task 9: Rich video detail UI

**Files:**
- Create: `web/src/features/feed/MediaFileDetails.tsx`
- Create: `web/src/features/feed/RemoteAvailabilityBadge.tsx`
- Modify: `web/src/features/feed/DesktopItemDetails.tsx`
- Modify: `web/src/features/feed/ItemDetailsSheet.tsx`
- Modify: `web/src/features/feed/FeedCard.tsx`
- Modify: `web/src/app/api.ts`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`
- Test: `web/src/features/feed/MediaFileDetails.test.tsx`

**Interfaces:**
- Consumes the rich item detail response from Task 7.
- Produces creator, Douyin statistics, local technical file rows, projection paths, checksums, and remote recheck action.

- [ ] **Step 1: Write failing tests** for all remote status labels, creator identity, file size/codec/dimensions/checksum, and recheck action.
- [ ] **Step 2: Run the focused Vitest file** and verify missing components fail.
- [ ] **Step 3: Implement desktop and mobile detail sections** using definition lists and collapsible asset rows.
- [ ] **Step 4: Add remote recheck feedback** without blocking local playback or deleting media.
- [ ] **Step 5: Run** `npm test && npm run build && npm run lint`.
- [ ] **Step 6: Commit** `feat: show rich Douyin and local file details`.

### Task 10: End-to-end verification and NAS deployment

**Files:**
- Modify: `Dockerfile` to install the distro `ffmpeg` package that supplies `ffprobe`.
- Verify: `compose.yaml` keeps the existing archive and Chromium-profile volumes unchanged.

**Interfaces:**
- Produces a verified NAS deployment and checkpoint tag.

- [ ] **Step 1: Run backend verification** `pytest -q` and `ruff check src tests`.
- [ ] **Step 2: Run frontend verification** `npm test && npm run build && npm run lint`.
- [ ] **Step 3: Inspect staged/committed files** and exclude secrets, database files, browser profiles, media, caches, and generated artifacts.
- [ ] **Step 4: Create a local checkpoint commit and annotated checkpoint tag.**
- [ ] **Step 5: Deploy without replacing `/archive/data`, `/archive/objects`, `/archive/library`, or the Chromium profile.**
- [ ] **Step 6: Verify migration counts and compare the existing completed-job/media totals before and after deployment.**
- [ ] **Step 7: Use Chrome to test desktop home, a category toggle, a video detail, and live updates.**
- [ ] **Step 8: Use an iPhone 15 Pro Max viewport to verify no horizontal overflow and 44px touch targets.**
- [ ] **Step 9: Create and tag the final local checkpoint; push only if the remote is a user-approved private GitLab.**
