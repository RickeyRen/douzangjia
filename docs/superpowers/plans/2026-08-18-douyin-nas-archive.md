# Douyin NAS Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy a NAS-only service that discovers every Douyin favorite folder every five minutes, permanently archives new video and gallery items into matching local folders, and serves a Douyin-like local browsing UI.

**Architecture:** A FastAPI API and a separate Python worker share SQLite WAL state and a ZFS-backed archive root. Playwright handles QR login and favorite discovery, while an idempotent downloader writes one canonical object and projects hard links into every collection folder; a React/Vite SPA provides setup, login, sync status, and immersive local playback.

**Tech Stack:** Python 3.12, FastAPI, aiosqlite, Pydantic Settings, Playwright Chromium, cryptography/Fernet, argon2-cffi, httpx, APScheduler, React 19, TypeScript, Vite, Vitest, Testing Library, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-18-douyin-nas-archive-design.md`

## Global Constraints

- Default UI language is Simplified Chinese; every user-visible string must have an English resource entry.
- Sync interval is five minutes and normal discovery-to-download latency must remain below ten minutes.
- Archive semantics are append-only: no remote removal, move, or rename deletes an archived file.
- Store canonical media once under `objects/`; expose collection views through hard links under `library/`.
- Bind the deployed service to the fnOS LAN interface only; do not create public ingress or port forwarding.
- Never log or return Douyin Cookie values, the archive master key, password hashes, or full signed media URLs.
- Do not claim real account synchronization before the user scans and a physical end-to-end favorite is downloaded and played.
- Use tests before implementation for every behavior change and create a local checkpoint commit after verified code changes.

---

### Task 1: Python application foundation and secure local administration

**Files:**
- Create: `pyproject.toml`
- Create: `src/douyin_archive/__init__.py`
- Create: `src/douyin_archive/config.py`
- Create: `src/douyin_archive/security.py`
- Create: `src/douyin_archive/api.py`
- Create: `src/douyin_archive/middleware.py`
- Create: `src/douyin_archive/routes/session.py`
- Create: `tests/test_config.py`
- Create: `tests/test_security.py`
- Create: `tests/test_health.py`
- Create: `tests/test_session_routes.py`

**Interfaces:**
- Produces: `Settings`, `PasswordHasher`, `CookieCipher`, `SessionService`, CSRF middleware, `create_app(settings: Settings) -> FastAPI`.
- Consumes: environment values `ARCHIVE_ROOT`, `ARCHIVE_MASTER_KEY`, `APP_BIND_HOST`, and `APP_PORT`.

- [ ] **Step 1: Write failing configuration and security tests**

```python
def test_settings_reject_root_archive(tmp_path):
    with pytest.raises(ValidationError):
        Settings(archive_root=Path("/"), master_key="x" * 44)

def test_cookie_cipher_round_trip(master_key):
    cipher = CookieCipher(master_key)
    encrypted = cipher.encrypt([{"name": "sessionid", "value": "secret"}])
    assert b"secret" not in encrypted
    assert cipher.decrypt(encrypted)[0]["value"] == "secret"

def test_password_hash_is_not_plaintext():
    encoded = PasswordHasher().hash("correct horse battery staple")
    assert "correct horse" not in encoded
    assert PasswordHasher().verify(encoded, "correct horse battery staple")

async def test_mutation_requires_csrf_token(authenticated_client):
    response = await authenticated_client.post("/api/sync")
    assert response.status_code == 403
    assert response.json()["code"] == "CSRF_REQUIRED"
```

- [ ] **Step 2: Run the focused tests and confirm missing-module failures**

Run: `uv run pytest tests/test_config.py tests/test_security.py tests/test_session_routes.py -q`
Expected: FAIL because `douyin_archive.config` and `douyin_archive.security` do not exist.

- [ ] **Step 3: Implement validated settings, redaction, Argon2id, and Fernet helpers**

```python
class Settings(BaseSettings):
    archive_root: Path
    master_key: SecretStr
    bind_host: str = "127.0.0.1"
    port: int = 8787
    sync_interval_seconds: int = 300

    @field_validator("archive_root")
    @classmethod
    def reject_broad_root(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        if resolved == Path("/"):
            raise ValueError("archive_root cannot be filesystem root")
        return resolved
```

- [ ] **Step 4: Add liveness and readiness endpoints**

```python
@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}

@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    checks = await request.app.state.readiness.check()
    return JSONResponse(checks, status_code=200 if checks["ready"] else 503)
```

- [ ] **Step 5: Add first-run setup, local sessions, and CSRF enforcement**

```python
@router.post("/api/setup", status_code=201)
async def setup(payload: SetupRequest, service: SessionService = Depends(get_sessions)):
    if await service.is_configured():
        raise ApiError("ALREADY_CONFIGURED", status_code=409)
    await service.create_admin(payload.password)
    return {"configured": True}
```

- [ ] **Step 6: Run tests and commit**

Run: `uv run pytest tests/test_config.py tests/test_security.py tests/test_health.py tests/test_session_routes.py -q`
Expected: PASS.

Commit: `git add pyproject.toml src/douyin_archive tests/test_config.py tests/test_security.py tests/test_health.py tests/test_session_routes.py && git commit -m "feat: establish secure archive service foundation"`

### Task 2: SQLite schema, repositories, and idempotent job state

**Files:**
- Create: `src/douyin_archive/db.py`
- Create: `src/douyin_archive/models.py`
- Create: `src/douyin_archive/repositories.py`
- Create: `src/douyin_archive/migrations/001_initial.sql`
- Create: `tests/test_database.py`
- Create: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `Settings.archive_root`.
- Produces: `Database.open()`, `Database.transaction()`, `ArchiveRepository`, `JobRepository.enqueue_unique()`, `JobRepository.claim_next()`.

- [ ] **Step 1: Write failing migration and idempotency tests**

```python
async def test_schema_enables_wal(database):
    row = await database.fetchone("PRAGMA journal_mode")
    assert row[0].lower() == "wal"

async def test_enqueue_unique_uses_kind_and_remote_id(job_repository):
    first = await job_repository.enqueue_unique("download", "734", {"url": "a"})
    second = await job_repository.enqueue_unique("download", "734", {"url": "b"})
    assert first.id == second.id
    assert await job_repository.count() == 1
```

- [ ] **Step 2: Run tests and confirm schema failures**

Run: `uv run pytest tests/test_database.py tests/test_jobs.py -q`
Expected: FAIL because the schema and repositories are absent.

- [ ] **Step 3: Implement migration runner and focused repository methods**

```sql
CREATE TABLE download_jobs (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  remote_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT NOT NULL,
  last_error_code TEXT,
  UNIQUE(kind, remote_id)
);
```

- [ ] **Step 4: Implement transactional job claiming**

```python
async def claim_next(self) -> DownloadJob | None:
    async with self.db.transaction(immediate=True):
        row = await self.db.fetchone(CLAIMABLE_JOB_SQL)
        if row is None:
            return None
        await self.db.execute(
            "UPDATE download_jobs SET status='running', attempts=attempts+1 WHERE id=?",
            (row["id"],),
        )
    return DownloadJob.from_row(row)
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/test_database.py tests/test_jobs.py -q`
Expected: PASS, including two concurrent claimers receiving different jobs.

Commit: `git add src/douyin_archive tests/test_database.py tests/test_jobs.py && git commit -m "feat: add persistent archive and job state"`

### Task 3: Canonical object storage, collection projections, and reliable downloads

**Files:**
- Create: `src/douyin_archive/paths.py`
- Create: `src/douyin_archive/storage.py`
- Create: `src/douyin_archive/downloader.py`
- Create: `tests/test_paths.py`
- Create: `tests/test_storage.py`
- Create: `tests/test_downloader.py`

**Interfaces:**
- Consumes: `RemoteItem`, `MediaAsset`, `ArchiveRepository`.
- Produces: `sanitize_segment()`, `ObjectStore.finalize()`, `CollectionProjector.project()`, `MediaDownloader.download()`.

- [ ] **Step 1: Write failing path and append-only projection tests**

```python
def test_sanitize_segment_preserves_chinese_and_blocks_traversal():
    assert sanitize_segment("../想去的/地方\x00") == "想去的_地方"

async def test_same_item_in_two_collections_uses_hardlinks(store, projector):
    object_file = await store.write_fixture("734", b"media")
    first = await projector.project("想去的地方", "标题", "734", object_file)
    second = await projector.project("好看的美女", "标题", "734", object_file)
    assert first.stat().st_ino == second.stat().st_ino == object_file.stat().st_ino
```

- [ ] **Step 2: Run tests and verify missing implementation failures**

Run: `uv run pytest tests/test_paths.py tests/test_storage.py tests/test_downloader.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement normalized paths and atomic object finalization**

```python
def sanitize_segment(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    cleaned = CONTROL_OR_SEPARATOR.sub("_", normalized).strip(" ._")
    return cleaned[:120] or "未命名"

async def finalize(self, part: Path, destination: Path) -> Path:
    await verify_nonempty(part)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(part, destination)
    return destination
```

- [ ] **Step 4: Implement streamed retries and integrity checks**

```python
async with self.client.stream("GET", asset.url, headers=headers) as response:
    response.raise_for_status()
    async with await anyio.open_file(part_path, "ab") as output:
        async for chunk in response.aiter_bytes(1024 * 1024):
            await output.write(chunk)
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/test_paths.py tests/test_storage.py tests/test_downloader.py -q`
Expected: PASS, including resume, truncated response, hard-link fallback, and orphan cleanup cases.

Commit: `git add src/douyin_archive tests/test_paths.py tests/test_storage.py tests/test_downloader.py && git commit -m "feat: archive media once and project collection folders"`

### Task 4: QR login browser and encrypted Douyin session lifecycle

**Files:**
- Create: `src/douyin_archive/auth_browser.py`
- Create: `src/douyin_archive/auth_service.py`
- Create: `src/douyin_archive/routes/auth.py`
- Create: `tests/test_auth_service.py`
- Create: `tests/test_auth_routes.py`

**Interfaces:**
- Consumes: `CookieCipher`, `ArchiveRepository`, Playwright `BrowserContext`.
- Produces: `AuthBrowser.start()`, `AuthService.begin_login()`, `AuthService.get_status()`, `/api/douyin/login` routes.

- [ ] **Step 1: Write failing auth-state tests with a fake browser**

```python
async def test_successful_login_encrypts_only_douyin_cookies(auth_service, fake_browser):
    fake_browser.cookies = [
        {"domain": ".douyin.com", "name": "sessionid", "value": "secret"},
        {"domain": ".example.com", "name": "other", "value": "discard"},
    ]
    status = await auth_service.complete_login("login-1")
    assert status.state == "authenticated"
    assert await auth_service.has_encrypted_value("discard") is False
```

- [ ] **Step 2: Run focused tests and verify failures**

Run: `uv run pytest tests/test_auth_service.py tests/test_auth_routes.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement bounded login sessions and cropped screenshots**

```python
class LoginSession:
    id: str
    state: Literal["starting", "awaiting_scan", "authenticated", "expired", "failed"]
    created_at: datetime
    screenshot_png: bytes | None

async def begin_login(self) -> LoginSession:
    session = await self.browser.start(timeout_seconds=300)
    self.sessions[session.id] = session
    return session
```

- [ ] **Step 4: Add redaction and session-expiry behavior**

```python
def public_status(session: LoginSession) -> dict[str, object]:
    return {
        "id": session.id,
        "state": session.state,
        "expiresAt": session.expires_at.isoformat(),
        "hasScreenshot": session.screenshot_png is not None,
    }
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/test_auth_service.py tests/test_auth_routes.py -q`
Expected: PASS with no cookie values in captured logs or responses.

Commit: `git add src/douyin_archive tests/test_auth_service.py tests/test_auth_routes.py && git commit -m "feat: add NAS-only Douyin QR login"`

### Task 5: Browser-first Douyin favorites provider

**Files:**
- Create: `src/douyin_archive/provider/base.py`
- Create: `src/douyin_archive/provider/douyin.py`
- Create: `src/douyin_archive/provider/normalizers.py`
- Create: `tests/fixtures/douyin/collections.json`
- Create: `tests/fixtures/douyin/collection_items.json`
- Create: `tests/test_provider_contract.py`
- Create: `tests/test_incremental_scan.py`

**Interfaces:**
- Consumes: encrypted Douyin cookies and Playwright browser context.
- Produces: `RemoteCollection`, `RemoteItem`, `RemotePage`, `MediaAsset`, `DouyinProvider.list_collections()`, `DouyinProvider.iter_collection_pages()`.

- [ ] **Step 1: Write provider contract and incremental-stop tests**

```python
async def test_collection_names_and_ids_are_normalized(provider):
    collections = await provider.list_collections()
    assert [(c.remote_id, c.name) for c in collections] == [
        ("1001", "想去的地方"),
        ("1002", "好看的美女"),
    ]

async def test_incremental_scan_stops_after_thirty_known_items(provider, known_ids):
    pages = [page async for page in provider.iter_collection_pages("1001", full_scan=False)]
    items = [item for page in pages for item in page.items]
    assert provider.requested_pages == 2
    assert all(item.aweme_id not in known_ids for item in items)
```

- [ ] **Step 2: Run contract tests and verify failures**

Run: `uv run pytest tests/test_provider_contract.py tests/test_incremental_scan.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement response capture and normalization**

```python
async def on_response(response: Response) -> None:
    path = urlparse(response.url).path
    if path in COLLECTION_ENDPOINTS and "application/json" in response.headers.get("content-type", ""):
        await captured.put((path, await response.json()))
```

- [ ] **Step 4: Implement page-wise iteration, known-item stopping, and risk signals**

```python
if item.aweme_id in known_ids:
    consecutive_known += 1
    if not full_scan and consecutive_known >= 30:
        return
else:
    consecutive_known = 0
    new_items.append(item)

if new_items:
    yield RemotePage(items=new_items, next_cursor=next_cursor)
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/test_provider_contract.py tests/test_incremental_scan.py -q`
Expected: PASS for default collection, custom folders, video, gallery, empty page, expired session, and repeated cursor fixtures.

Commit: `git add src/douyin_archive/provider tests/fixtures/douyin tests/test_provider_contract.py tests/test_incremental_scan.py && git commit -m "feat: discover Douyin favorite folders and items"`

### Task 6: Sync orchestration, scheduler, retry policy, and notifications

**Files:**
- Create: `src/douyin_archive/sync_service.py`
- Create: `src/douyin_archive/worker.py`
- Create: `src/douyin_archive/scheduler.py`
- Create: `src/douyin_archive/notifications.py`
- Create: `src/douyin_archive/routes/sync.py`
- Create: `tests/test_sync_service.py`
- Create: `tests/test_scheduler.py`

**Interfaces:**
- Consumes: `DouyinProvider`, `ArchiveRepository`, `JobRepository`, `MediaDownloader`, `CollectionProjector`.
- Produces: `SyncService.run()`, `Worker.run_forever()`, five-minute schedule, `/api/sync` and `/api/sync/runs`.

- [ ] **Step 1: Write failing full-backfill and retry tests**

```python
async def test_full_sync_commits_each_page(sync_service, fake_provider, repository):
    result = await sync_service.run(full_scan=True)
    assert result.discovered == 41
    assert repository.page_commit_count == 3

async def test_rate_limit_sets_cooldown(worker, job_repository):
    await worker.handle(raising_job(RateLimitedError(retry_after=900)))
    job = await job_repository.get(1)
    assert job.status == "retry"
    assert job.next_attempt_at >= utcnow() + timedelta(minutes=14)
```

- [ ] **Step 2: Run tests and verify failures**

Run: `uv run pytest tests/test_sync_service.py tests/test_scheduler.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement page commits and idempotent download creation**

```python
async for page in self.provider.iter_collection_pages(collection.remote_id, full_scan=full_scan):
    async with self.repository.transaction():
        for item in page.items:
            await self.repository.upsert_item(item)
            await self.repository.link_collection(collection, item)
            await self.jobs.enqueue_unique("download", item.aweme_id, item.model_dump())
```

- [ ] **Step 4: Add scheduler and terminal error codes**

```python
scheduler.add_job(
    sync_service.run_incremental,
    "interval",
    seconds=settings.sync_interval_seconds,
    max_instances=1,
    coalesce=True,
)
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/test_sync_service.py tests/test_scheduler.py -q`
Expected: PASS for restart recovery, auth expiry, storage full, 404 media, 429 cooldown, and duplicate schedule cases.

Commit: `git add src/douyin_archive tests/test_sync_service.py tests/test_scheduler.py && git commit -m "feat: schedule permanent incremental archives"`

### Task 7: Feed, item, collection, task, and Range media APIs

**Files:**
- Create: `src/douyin_archive/routes/feed.py`
- Create: `src/douyin_archive/routes/media.py`
- Create: `src/douyin_archive/routes/jobs.py`
- Create: `tests/test_feed_api.py`
- Create: `tests/test_media_range.py`

**Interfaces:**
- Consumes: `ArchiveRepository` and canonical `media_files` paths.
- Produces: `/api/collections`, `/api/feed`, `/api/items/{id}`, `/api/media/{id}`, `/api/jobs`.

- [ ] **Step 1: Write failing cursor and Range tests**

```python
async def test_feed_cursor_has_no_duplicates(client, seeded_items):
    first = await client.get("/api/feed?limit=2")
    second = await client.get(f"/api/feed?limit=2&cursor={first.json()['nextCursor']}")
    assert set(ids(first)) & set(ids(second)) == set()

async def test_media_range_returns_partial_bytes(client, media_file):
    response = await client.get(f"/api/media/{media_file.id}", headers={"Range": "bytes=2-5"})
    assert response.status_code == 206
    assert response.content == b"2345"
    assert response.headers["content-range"] == "bytes 2-5/10"
```

- [ ] **Step 2: Run API tests and verify failures**

Run: `uv run pytest tests/test_feed_api.py tests/test_media_range.py -q`
Expected: FAIL.

- [ ] **Step 3: Implement stable `(first_seen_at, aweme_id)` cursors**

```python
cursor = Cursor.decode(query.cursor) if query.cursor else None
rows = await repository.list_feed(
    collection_id=query.collection_id,
    media_type=query.media_type,
    search=query.search,
    before=cursor,
    limit=query.limit + 1,
)
```

- [ ] **Step 4: Implement authenticated single-range responses**

```python
start, end = parse_range(request.headers.get("range"), file_size)
headers = {"Accept-Ranges": "bytes", "Content-Range": f"bytes {start}-{end}/{file_size}"}
return StreamingResponse(iter_file(path, start, end), status_code=206, headers=headers)
```

- [ ] **Step 5: Run tests and commit**

Run: `uv run pytest tests/test_feed_api.py tests/test_media_range.py -q`
Expected: PASS, including 416 ranges, missing files, traversal attempts, and unauthenticated requests.

Commit: `git add src/douyin_archive/routes tests/test_feed_api.py tests/test_media_range.py && git commit -m "feat: expose archived collections and local media"`

### Task 8: Responsive Douyin-like browsing and management SPA

**Files:**
- Create: `web/package.json`
- Create: `web/vite.config.ts`
- Create: `web/src/main.tsx`
- Create: `web/src/app/App.tsx`
- Create: `web/src/app/api.ts`
- Create: `web/src/features/setup/SetupPage.tsx`
- Create: `web/src/features/auth/DouyinLoginPage.tsx`
- Create: `web/src/features/feed/FeedPage.tsx`
- Create: `web/src/features/feed/FeedCard.tsx`
- Create: `web/src/features/feed/GalleryViewer.tsx`
- Create: `web/src/features/navigation/CollectionRail.tsx`
- Create: `web/src/features/status/StatusPage.tsx`
- Create: `web/src/i18n/zh-CN.ts`
- Create: `web/src/i18n/en.ts`
- Create: `web/src/styles/tokens.css`
- Create: `web/src/styles/app.css`
- Create: `web/src/features/feed/FeedPage.test.tsx`
- Create: `web/src/features/auth/DouyinLoginPage.test.tsx`

**Interfaces:**
- Consumes: JSON APIs from Tasks 4, 6, and 7.
- Produces: setup flow, QR login flow, collection navigation, immersive feed, gallery viewer, sync status, and language switch.

- [ ] **Step 1: Write failing feed and login UI tests**

```tsx
it("switches folders and keeps one active feed card", async () => {
  render(<FeedPage />, { wrapper: testApp });
  await user.click(await screen.findByRole("button", { name: "好看的美女" }));
  expect(await screen.findByText("来自 好看的美女")).toBeVisible();
  expect(screen.getAllByTestId("feed-card").filter(isPlaying)).toHaveLength(1);
});

it("shows the QR screenshot without exposing cookie text", async () => {
  render(<DouyinLoginPage />, { wrapper: testApp });
  await user.click(screen.getByRole("button", { name: "登录抖音" }));
  expect(await screen.findByAltText("抖音登录二维码")).toBeVisible();
  expect(screen.queryByText(/sessionid/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run Vitest and verify component failures**

Run: `cd web && npm test -- --run`
Expected: FAIL because pages and components are absent.

- [ ] **Step 3: Implement scroll-snap feed and local playback**

```css
.feedViewport {
  height: 100dvh;
  overflow-y: auto;
  scroll-snap-type: y mandatory;
  background: #08090b;
}
.feedCard {
  min-height: 100dvh;
  scroll-snap-align: start;
  scroll-snap-stop: always;
}
```

- [ ] **Step 4: Implement responsive collection navigation, gallery gestures, and i18n**

```tsx
const active = useIntersectionActiveCard(cardRefs, { threshold: 0.72 });
return items.map(item => (
  <FeedCard key={item.awemeId} item={item} playing={active === item.awemeId} />
));
```

- [ ] **Step 5: Run UI tests, production build, and commit**

Run: `cd web && npm test -- --run && npm run build`
Expected: all tests PASS and `web/dist/index.html` exists.

Commit: `git add web && git commit -m "feat: add immersive local favorites browser"`

### Task 9: Docker image, Compose, operations, and NAS deployment

**Files:**
- Create: `Dockerfile`
- Create: `compose.yaml`
- Create: `.dockerignore`
- Create: `.env.example`
- Create: `scripts/generate_master_key.py`
- Create: `scripts/smoke.sh`
- Create: `docs/operations.md`
- Create: `tests/test_compose_config.py`

**Interfaces:**
- Consumes: Python API/worker entries and `web/dist`.
- Produces: fixed-tag local image, persistent `/archive`, LAN-only port, health checks, backup and rollback instructions.

- [ ] **Step 1: Write failing Compose policy tests**

```python
def test_compose_has_no_public_wildcard(compose):
    ports = compose["services"]["api"]["ports"]
    assert ports == ["${LAN_IP}:8787:8787"]
    assert compose["services"]["api"]["user"] == "${PUID}:${PGID}"
    assert compose["services"]["worker"]["volumes"] == compose["services"]["api"]["volumes"]
```

- [ ] **Step 2: Run policy test and verify failure**

Run: `uv run pytest tests/test_compose_config.py -q`
Expected: FAIL because Compose is absent.

- [ ] **Step 3: Implement multi-stage image and pinned Compose configuration**

```yaml
services:
  api:
    image: douyin-archive:0.1.0
    user: "${PUID}:${PGID}"
    ports:
      - "${LAN_IP}:8787:8787"
    volumes:
      - "${ARCHIVE_HOST_PATH}:/archive"
    restart: unless-stopped
```

- [ ] **Step 4: Add smoke checks and operations guide**

```sh
curl --fail --silent "http://${LAN_IP}:8787/health/live"
curl --fail --silent "http://${LAN_IP}:8787/health/ready"
docker compose ps --format json
```

- [ ] **Step 5: Run complete local verification and commit**

Run: `uv run pytest -q && cd web && npm test -- --run && npm run build && cd .. && docker compose config && docker build -t douyin-archive:0.1.0 .`
Expected: all tests/builds PASS, Compose resolves, image builds.

Commit: `git add Dockerfile compose.yaml .dockerignore .env.example scripts docs/operations.md tests/test_compose_config.py && git commit -m "ops: package Douyin archive for fnOS"`

- [ ] **Step 6: Deploy to fnOS without exposing secrets in command output**

Run: copy the committed source bundle to an explicit application directory on `192.168.0.6`, generate the master key directly on the NAS with mode `600`, build `douyin-archive:0.1.0`, and start Compose.

Expected: `health/live` and `health/ready` are both 200 from the LAN; persistent directories are owned by `RENJIAWEI`; no Douyin Cookie exists before scanning.

### Task 10: QR handoff and real end-to-end acceptance

**Files:**
- Modify only if live evidence reveals a provider compatibility defect.
- Create: `docs/acceptance/2026-08-18-fnos-live.md`

**Interfaces:**
- Consumes: deployed service and user-completed QR scan.
- Produces: evidence for login, folder discovery, initial download, local playback, and ten-minute incremental behavior.

- [ ] **Step 1: Ask the user to open the LAN URL and scan**

Expected: the user confirms the Douyin app approved the login; no password is requested by the archive service.

- [ ] **Step 2: Verify authenticated state without displaying cookies**

Run: query only the public auth state and service logs with redaction enabled.
Expected: state is `authenticated`, Cookie validation succeeds, no Cookie value appears.

- [ ] **Step 3: Run first full sync and verify real folder names**

Expected: collections include `想去的地方` and `好看的美女`; matching `library/` directories exist; discovery count is nonzero.

- [ ] **Step 4: Verify one real media object and local playback**

Expected: canonical object is complete, collection entry is a hard link, `/api/media/{id}` returns valid Range bytes, and the browser plays or displays it.

- [ ] **Step 5: Verify ten-minute incremental acceptance**

Expected: after the user adds one test favorite, the item is discovered, downloaded, projected, and visible in the correct collection within ten minutes.

- [ ] **Step 6: Record evidence, run final verification, and create checkpoint**

Run: `uv run pytest -q && cd web && npm test -- --run && npm run build`
Expected: all automated checks PASS and the acceptance document distinguishes build, deployment, login, discovery, download, and end-to-end timing.

Commit: `git add src web docs/acceptance/2026-08-18-fnos-live.md && git commit -m "test: record fnOS end-to-end archive acceptance"`
