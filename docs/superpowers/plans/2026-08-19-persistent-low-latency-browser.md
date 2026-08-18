# Persistent Low-Latency Douyin Browser Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse one durable Chromium device profile for Douyin login and collection discovery, and replace queued MJPEG/HTTP interaction with a latest-frame CDP/WebSocket path.

**Architecture:** A `BrowserCoordinator` owns one Playwright persistent context rooted under the archive volume and leases serialized pages to login and discovery consumers. A focused screencast hub bridges CDP `Page.screencastFrame` events to authenticated WebSockets with a one-frame mailbox, while the React client renders binary JPEG frames to a canvas and sends coalesced input over the same socket.

**Tech Stack:** Python 3.13, FastAPI/Starlette WebSocket, Playwright async API and CDP, Pydantic Settings, React 19, TypeScript, Vitest, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-19-persistent-low-latency-browser-design.md`

## Global Constraints

- Chromium profile path is fixed below `ARCHIVE_ROOT/data/chromium-profile` and must have mode `0700`.
- Full profile contents stay out of Git, Docker build context, logs and API responses.
- The existing encrypted `auth_sessions.encrypted_cookies` record remains authoritative for sync readiness.
- WebSocket handshake requires a valid local admin session and a same-host `Origin`.
- Only digits, `Backspace`, `Enter` and `Tab` are accepted as keyboard input.
- Keep MJPEG and HTTP pointer/key routes as one-version compatibility fallbacks.
- Do not kill an unknown Chromium process when the profile is locked.
- Build, deploy, container health, login restoration, sync and interaction latency are reported separately.

---

### Task 1: Private Persistent Profile Store

**Files:**
- Create: `src/douyin_archive/browser_profile.py`
- Create: `tests/test_browser_profile.py`
- Modify: `src/douyin_archive/config.py`
- Modify: `.gitignore`
- Modify: `.dockerignore`

**Interfaces:**
- Produces: `BrowserProfileStore(root: Path)` with `prepare() -> Path`, `quarantine(reason: str) -> Path`, and `profile_path: Path`.
- Produces: `Settings.browser_profile_path -> Path`, always resolved as `archive_root / "data" / "chromium-profile"`.

- [ ] **Step 1: Write failing profile permission and quarantine tests**

```python
def test_prepare_creates_private_profile_directory(tmp_path: Path) -> None:
    store = BrowserProfileStore(tmp_path)
    path = store.prepare()
    assert path == tmp_path / "data" / "chromium-profile"
    assert stat.S_IMODE(path.stat().st_mode) == 0o700

def test_quarantine_preserves_corrupt_profile(tmp_path: Path) -> None:
    store = BrowserProfileStore(tmp_path)
    store.prepare()
    (store.profile_path / "marker").write_text("keep", encoding="utf-8")
    quarantined = store.quarantine("corrupt")
    assert (quarantined / "marker").read_text(encoding="utf-8") == "keep"
    assert not store.profile_path.exists()
```

- [ ] **Step 2: Run the tests and confirm the new module is missing**

Run: `.venv/bin/pytest -q tests/test_browser_profile.py`

Expected: FAIL during import with `ModuleNotFoundError: douyin_archive.browser_profile`.

- [ ] **Step 3: Implement the focused store and derived setting**

```python
class BrowserProfileStore:
    def __init__(self, archive_root: Path) -> None:
        self.profile_path = archive_root / "data" / "chromium-profile"

    def prepare(self) -> Path:
        self.profile_path.mkdir(parents=True, exist_ok=True)
        os.chmod(self.profile_path, 0o700)
        if stat.S_IMODE(self.profile_path.stat().st_mode) != 0o700:
            raise PermissionError("browser profile must have mode 0700")
        return self.profile_path

    def quarantine(self, reason: str) -> Path:
        suffix = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        target = self.profile_path.with_name(f"chromium-profile.{reason}.{suffix}")
        self.profile_path.rename(target)
        return target
```

Add an immutable `browser_profile_path` property to `Settings`; add `archive-data/` and `chromium-profile*` protection patterns to both ignore files.

- [ ] **Step 4: Run focused tests and lint**

Run: `.venv/bin/pytest -q tests/test_browser_profile.py tests/test_config.py && .venv/bin/ruff check src tests`

Expected: all selected tests pass and Ruff reports `All checks passed!`.

- [ ] **Step 5: Commit the private profile store**

```bash
git add src/douyin_archive/browser_profile.py src/douyin_archive/config.py tests/test_browser_profile.py .gitignore .dockerignore
git commit -m "feat: add private persistent browser profile"
```

### Task 2: Single Persistent Browser Coordinator

**Files:**
- Create: `src/douyin_archive/browser_coordinator.py`
- Create: `tests/test_browser_coordinator.py`
- Modify: `src/douyin_archive/browser_launch.py`
- Modify: `src/douyin_archive/api.py`
- Modify: `src/douyin_archive/auth_browser.py`
- Modify: `src/douyin_archive/runtime.py`

**Interfaces:**
- Consumes: `BrowserProfileStore.prepare() -> Path`.
- Produces: `BrowserCoordinator(profile_store, *, launch_options=chromium_launch_options)`.
- Produces: `start()`, `close()`, `new_page(*, viewport: tuple[int, int])`, `release_page(page)`, `cookies()`, `add_cookies(cookies)`, and `is_douyin_authenticated()`.
- Produces: `CoordinatorPageLease`, an async context manager that holds the coordinator lock and releases its page without closing the persistent context.

- [ ] **Step 1: Write failing coordinator lifecycle tests with Playwright doubles**

```python
async def test_coordinator_launches_persistent_context_once(tmp_path: Path) -> None:
    playwright = FakePlaywright()
    coordinator = BrowserCoordinator(
        BrowserProfileStore(tmp_path), playwright_factory=lambda: playwright
    )
    await coordinator.start()
    await coordinator.start()
    assert playwright.chromium.persistent_launches == [
        tmp_path / "data" / "chromium-profile"
    ]

async def test_page_leases_are_serialized(tmp_path: Path) -> None:
    coordinator = prepared_fake_coordinator(tmp_path)
    first = await coordinator.acquire_page(viewport=(1280, 800))
    waiting = asyncio.create_task(coordinator.acquire_page(viewport=(1440, 1000)))
    await asyncio.sleep(0)
    assert not waiting.done()
    await first.release()
    second = await waiting
    await second.release()
```

- [ ] **Step 2: Verify the coordinator tests fail**

Run: `.venv/bin/pytest -q tests/test_browser_coordinator.py`

Expected: FAIL because `BrowserCoordinator` does not exist.

- [ ] **Step 3: Implement one persistent context and serialized page leases**

Launch with:

```python
self.context = await self.playwright.chromium.launch_persistent_context(
    str(self.profile_store.prepare()),
    **chromium_persistent_launch_options(),
    viewport={"width": 1280, "height": 800},
    locale="zh-CN",
    timezone_id="Asia/Shanghai",
)
```

Use one `asyncio.Lock` for page leases. Never terminate a process on profile-lock errors. Translate a Playwright message containing `ProcessSingleton` or `profile in use` into `BrowserProfileLocked`.

- [ ] **Step 4: Inject the coordinator into app lifespan and AuthBrowser**

Create the coordinator before `AuthService` in `create_app()` lifespan. `AuthBrowser` receives it and stores only page leases per login id; `close(login_id)` releases the page but does not close the coordinator. App shutdown calls `await coordinator.close()` after runtime shutdown.

- [ ] **Step 5: Add startup authentication recovery tests**

```python
async def test_startup_restores_douyin_login_without_new_qr(tmp_path: Path) -> None:
    coordinator = FakeCoordinator(authenticated=True)
    runtime = ArchiveRuntime(..., browser_coordinator=coordinator)
    await runtime.start()
    assert coordinator.login_pages_created == 0
    assert runtime.sync_triggered is True
```

Implement `BrowserCoordinator.is_douyin_authenticated()` by checking required `.douyin.com` session cookies and, when necessary, loading the favorites URL in a leased page to reject a redirect to login.

- [ ] **Step 6: Run coordinator, auth and runtime tests**

Run: `.venv/bin/pytest -q tests/test_browser_coordinator.py tests/test_auth_browser.py tests/test_auth_service.py tests/test_runtime.py tests/test_auth_routes.py && .venv/bin/ruff check src tests`

Expected: all selected tests pass.

- [ ] **Step 7: Commit the persistent coordinator**

```bash
git add src/douyin_archive/browser_coordinator.py src/douyin_archive/browser_launch.py src/douyin_archive/api.py src/douyin_archive/auth_browser.py src/douyin_archive/runtime.py tests/test_browser_coordinator.py tests/test_auth_browser.py tests/test_runtime.py
git commit -m "feat: reuse one persistent Douyin browser"
```

### Task 3: Reuse the Coordinator for Collection Discovery

**Files:**
- Modify: `src/douyin_archive/provider/douyin.py`
- Modify: `src/douyin_archive/runtime.py`
- Create: `tests/test_provider_douyin_browser.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Consumes: `BrowserCoordinator.acquire_page(viewport=(1440, 1000)) -> CoordinatorPageLease`.
- Produces: `PlaywrightDouyinSource(coordinator: BrowserCoordinator)`; `close()` releases only its lease.
- Changes: `RuntimeSyncCoordinator` accepts `source_factory: Callable[[], RawPageSource]` rather than a cookie argument.

- [ ] **Step 1: Write failing discovery reuse tests**

```python
async def test_source_uses_coordinator_page_without_launching_browser() -> None:
    coordinator = FakeCoordinator()
    source = PlaywrightDouyinSource(coordinator)
    await source.open()
    assert coordinator.requested_viewports == [(1440, 1000)]
    await source.close()
    assert coordinator.released_pages == 1
    assert coordinator.closed is False
```

- [ ] **Step 2: Run the discovery tests and confirm constructor mismatch**

Run: `.venv/bin/pytest -q tests/test_provider_douyin_browser.py tests/test_runtime.py`

Expected: FAIL because `PlaywrightDouyinSource` still expects cookies and launches its own browser.

- [ ] **Step 3: Refactor the source to use a page lease**

Remove Playwright/browser/context ownership from `PlaywrightDouyinSource`. In `open()`, acquire one page lease, register the response callback, and reuse cookies already present in the persistent context. In `close()`, unregister the response handler, release the lease, clear response queues and retain no page reference.

- [ ] **Step 4: Update runtime source construction and expired-session handling**

Before discovery, call `coordinator.is_douyin_authenticated()`. If false, mark `auth_sessions.status='expired'` and run `_ExpiredProvider`; if true, create `PlaywrightDouyinSource(coordinator)`. Preserve serialized sync execution.

- [ ] **Step 5: Run provider and runtime tests**

Run: `.venv/bin/pytest -q tests/test_provider_douyin_browser.py tests/test_runtime.py tests/test_sync_service.py && .venv/bin/ruff check src tests`

Expected: all tests pass and the fake coordinator is not closed by a sync source.

- [ ] **Step 6: Commit shared discovery browser support**

```bash
git add src/douyin_archive/provider/douyin.py src/douyin_archive/runtime.py tests/test_provider_douyin_browser.py tests/test_runtime.py
git commit -m "refactor: share persistent browser with sync"
```

### Task 4: Latest-Frame CDP Screencast Hub

**Files:**
- Create: `src/douyin_archive/browser_stream.py`
- Create: `tests/test_browser_stream.py`
- Modify: `src/douyin_archive/auth_browser.py`

**Interfaces:**
- Produces: `LatestFrameMailbox.put(frame: bytes)`, `get() -> bytes`, `close()`.
- Produces: `CdpScreencast(page, *, quality=68, width=1280, height=800)` with `start()`, `subscribe()`, and `close()`.
- Produces: `AuthBrowser.screencast(login_id) -> CdpScreencast`.

- [ ] **Step 1: Write failing latest-frame and CDP ack tests**

```python
async def test_mailbox_replaces_unsent_frame() -> None:
    mailbox = LatestFrameMailbox()
    mailbox.put(b"old")
    mailbox.put(b"latest")
    assert await mailbox.get() == b"latest"

async def test_screencast_acknowledges_each_cdp_frame() -> None:
    cdp = FakeCdpSession()
    stream = CdpScreencast(FakePage(cdp))
    await stream.start()
    await cdp.emit("Page.screencastFrame", {"data": JPEG_B64, "sessionId": 41})
    assert cdp.commands[-1] == (
        "Page.screencastFrameAck", {"sessionId": 41}
    )
```

- [ ] **Step 2: Verify stream tests fail**

Run: `.venv/bin/pytest -q tests/test_browser_stream.py`

Expected: FAIL because `browser_stream` does not exist.

- [ ] **Step 3: Implement CDP session lifecycle and one-frame subscriber mailboxes**

Start with:

```python
await cdp.send("Page.startScreencast", {
    "format": "jpeg",
    "quality": 68,
    "maxWidth": 1280,
    "maxHeight": 800,
    "everyNthFrame": 1,
})
```

Decode frame `data` with `base64.b64decode`, ack immediately, and replace each subscriber's pending frame. `close()` sends `Page.stopScreencast`, detaches the CDP session and wakes blocked subscribers.

- [ ] **Step 4: Run stream and browser tests**

Run: `.venv/bin/pytest -q tests/test_browser_stream.py tests/test_auth_browser.py && .venv/bin/ruff check src tests`

Expected: tests pass with no unclosed task warnings.

- [ ] **Step 5: Commit the screencast hub**

```bash
git add src/douyin_archive/browser_stream.py src/douyin_archive/auth_browser.py tests/test_browser_stream.py tests/test_auth_browser.py
git commit -m "feat: stream only the latest browser frame"
```

### Task 5: Authenticated WebSocket Transport

**Files:**
- Create: `src/douyin_archive/browser_socket.py`
- Create: `tests/test_browser_socket.py`
- Modify: `src/douyin_archive/api.py`
- Modify: `src/douyin_archive/auth_service.py`

**Interfaces:**
- Consumes: `AuthBrowser.screencast(login_id)`, existing `pointer()` and `key()`.
- Produces: WebSocket route `/ws/douyin/login/{login_id}`.
- Produces messages: binary JPEG frames and JSON `{type:"status", state, width, height, transport}`.
- Consumes messages: `{type:"pointer", action, x, y}` and `{type:"key", key}`.

- [ ] **Step 1: Write failing WebSocket authentication and transport tests**

```python
def test_browser_socket_rejects_missing_admin_session(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(
            "/ws/douyin/login/login-1",
            headers={"origin": "http://testserver"},
        ):
            pass
    assert error.value.code == 4401

def test_browser_socket_sends_binary_latest_frame(authenticated_client) -> None:
    with authenticated_client.websocket_connect(
        "/ws/douyin/login/login-1",
        headers={"origin": "http://testserver"},
    ) as socket:
        status = socket.receive_json()
        frame = socket.receive_bytes()
    assert status["transport"] == "cdp"
    assert frame.startswith(b"\xff\xd8")
```

- [ ] **Step 2: Verify socket tests fail with route not found**

Run: `.venv/bin/pytest -q tests/test_browser_socket.py`

Expected: FAIL because the WebSocket route is absent.

- [ ] **Step 3: Extract reusable session validation from HTTP middleware**

Move token decoding into `SessionCodec.is_valid(token: str | None) -> bool` in `api.py` or a focused `session_auth.py`. Use the same codec for HTTP and WebSocket. Parse the `Origin` header and compare its normalized hostname and effective port with the request `Host` header; accept the configured NAS host and TestClient's `testserver`, reject missing, malformed or mismatched origins with code `4403`.

- [ ] **Step 4: Implement concurrent send and receive loops**

Use an `asyncio.TaskGroup`: sender writes the initial status and each mailbox frame; receiver validates Pydantic discriminated messages before forwarding them. A disconnect cancels the sibling task and unsubscribes the mailbox. Invalid input closes with `4400`; ended login closes with `4404`.

- [ ] **Step 5: Add fallback metadata and no-secret logging tests**

When screencast creation raises `CdpUnavailable`, send `{type:"status", transport:"mjpeg"}` and close normally so the client selects the legacy stream. Assert logs do not contain key values, cookies or full query strings.

- [ ] **Step 6: Run API, socket and security tests**

Run: `.venv/bin/pytest -q tests/test_browser_socket.py tests/test_auth_routes.py tests/test_session_routes.py tests/test_security.py && .venv/bin/ruff check src tests`

Expected: all tests pass.

- [ ] **Step 7: Commit the WebSocket transport**

```bash
git add src/douyin_archive/browser_socket.py src/douyin_archive/api.py src/douyin_archive/auth_service.py tests/test_browser_socket.py tests/test_auth_routes.py tests/test_session_routes.py
git commit -m "feat: add authenticated browser websocket"
```

### Task 6: Canvas Client, Reconnection and Input Coalescing

**Files:**
- Create: `web/src/features/auth/useDouyinBrowserSocket.ts`
- Create: `web/src/features/auth/useDouyinBrowserSocket.test.ts`
- Modify: `web/src/features/auth/DouyinLoginPage.tsx`
- Modify: `web/src/features/auth/DouyinLoginPage.test.tsx`
- Modify: `web/src/i18n/messages.ts`

**Interfaces:**
- Produces: `useDouyinBrowserSocket({loginId, canvasRef, onStatus})` returning `{transport, connected, sendPointer, sendKey}`.
- Consumes: `/ws/douyin/login/{loginId}`, binary JPEG frames and status JSON.
- Falls back to `douyinStreamUrl(loginId)` only when server status reports `transport:"mjpeg"` or WebSocket retries are exhausted.

- [ ] **Step 1: Write failing binary-frame and latest-draw hook tests**

```typescript
it("draws only the latest decoded frame", async () => {
  const socket = installFakeWebSocket();
  const bitmap = vi.spyOn(globalThis, "createImageBitmap");
  renderHook(() => useDouyinBrowserSocket(options));
  socket.emitBlob(firstJpeg);
  socket.emitBlob(latestJpeg);
  await vi.waitFor(() => expect(drawImage).toHaveBeenCalledTimes(1));
  expect(bitmap).toHaveBeenLastCalledWith(latestJpeg);
});
```

- [ ] **Step 2: Verify hook tests fail**

Run: `npm --prefix web test -- --run useDouyinBrowserSocket.test.ts`

Expected: FAIL because the hook does not exist.

- [ ] **Step 3: Implement WebSocket lifecycle and latest-frame canvas rendering**

Set `socket.binaryType = "blob"`. Store only the newest pending Blob while `createImageBitmap` is decoding. Draw to a 1280×800 canvas, close the bitmap, then decode the newest replacement if one arrived. Reconnect after 250 ms, 500 ms, 1 s, 2 s and 5 s; reset the delay after a successful connection.

- [ ] **Step 4: Coalesce pointer movement and send critical events immediately**

Queue only the newest pointer move and flush it in `requestAnimationFrame`. Send `down`, `up`, digits, Backspace, Enter and Tab immediately. Preserve pointer capture and the existing 12-pixel server drag threshold.

- [ ] **Step 5: Replace the live `<img>` with a canvas plus explicit MJPEG fallback**

The canvas keeps `object-contain`, fullscreen sizing, keyboard focus and the existing overlay. Add Chinese and English strings for `liveConnected`, `liveReconnecting`, and `liveFallback`; no hard-coded UI copy in the component.

- [ ] **Step 6: Run frontend tests and production build**

Run: `npm --prefix web test -- --run && npm --prefix web run build`

Expected: all Vitest files pass and Vite produces hashed assets without TypeScript errors.

- [ ] **Step 7: Commit the low-latency client**

```bash
git add web/src/features/auth/useDouyinBrowserSocket.ts web/src/features/auth/useDouyinBrowserSocket.test.ts web/src/features/auth/DouyinLoginPage.tsx web/src/features/auth/DouyinLoginPage.test.tsx web/src/i18n/messages.ts
git commit -m "feat: render low-latency browser stream"
```

### Task 7: Migration, Full Verification and NAS Deployment

**Files:**
- Modify: `README.md`
- Modify: `compose.yaml`
- Modify: `tests/test_config.py`
- Modify: `docs/superpowers/specs/2026-08-19-persistent-low-latency-browser-design.md` only if implementation evidence requires a factual correction.

**Interfaces:**
- Consumes all prior tasks.
- Produces a deployed NAS image with persistent profile at `/archive/data/chromium-profile` and both CDP/WebSocket and MJPEG transports.

- [ ] **Step 1: Add migration and Compose configuration tests**

Assert the profile path stays under `ARCHIVE_ROOT`, Compose mounts only `/archive`, rootfs remains read-only, and the health check does not require an active Douyin login.

- [ ] **Step 2: Document profile security and recovery**

README must state that the profile is mode `0700` but readable by NAS administrators/root, show its fixed path, explain that deleting it forces a new-device login, and describe how to move a quarantined profile back only while the container is stopped.

- [ ] **Step 3: Run the complete local verification suite**

Run:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check src tests
npm --prefix web test -- --run
npm --prefix web run build
docker compose config
git diff --check
```

Expected: all backend and frontend tests pass, build completes, Compose config renders and diff check is clean.

- [ ] **Step 4: Create the pre-deployment checkpoint**

```bash
git add README.md compose.yaml tests/test_config.py docs/superpowers/specs/2026-08-19-persistent-low-latency-browser-design.md
git commit -m "docs: describe persistent browser operations"
```

- [ ] **Step 5: Copy only tracked source to the NAS and build**

Use SSH key `/Users/renjiawei/.ssh/all_server_key`, destination `/vol3/1000/docker/douyin-nas-archive`, preserve the NAS `.env`, and exclude `.git`, virtual environments, node modules, build output, profile data and archive data. Build `douyin-nas-archive:local`, then recreate only the `archive` service.

- [ ] **Step 6: Verify deployment layers independently**

Confirm:

```text
container: running/healthy
/health/ready: archiveRoot=ok, browserProfile=ok
runtime image: new sha256
profile: /archive/data/chromium-profile mode 0700
transport: WebSocket status reports cdp
```

- [ ] **Step 7: Perform real persistent-login acceptance**

Complete one user-authorized Douyin login, verify `auth_sessions` is authenticated without printing cookies, trigger and finish one real incremental sync, restart the container once, and verify the app restores authenticated state without presenting a QR code.

- [ ] **Step 8: Measure low-latency interaction and fallback**

Record observed frame cadence over 10 seconds, verify a click and drag change the remote page without replaying old frames, disconnect the WebSocket to confirm automatic reconnect, and force the test-only CDP-unavailable path to confirm MJPEG fallback.

- [ ] **Step 9: Create the final checkpoint and report remote backup status**

Run the full verification suite once more, commit any evidence-only corrections, and report that no GitLab push occurred unless `git remote -v` confirms an approved private GitLab URL. Never force push or create a public remote.
