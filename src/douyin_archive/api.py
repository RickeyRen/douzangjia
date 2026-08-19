import asyncio
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .browser_coordinator import BrowserCoordinator
from .browser_profile import BrowserProfileStore
from .browser_socket import handle_browser_socket
from .config import Settings
from .db import Database
from .library_repository import LibraryRepository
from .repositories import ArchiveRepository, JobRepository
from .security import CookieCipher, PasswordHasher
from .session_auth import SessionCodec

SESSION_COOKIE = "archive_session"
CSRF_COOKIE = "archive_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
MJPEG_BOUNDARY = "frame"
MJPEG_FRAME_INTERVAL_SECONDS = 1 / 12


def _mjpeg_chunk(frame: bytes) -> bytes:
    return (
        f"--{MJPEG_BOUNDARY}\r\n".encode()
        + b"Content-Type: image/jpeg\r\n"
        + f"Content-Length: {len(frame)}\r\n\r\n".encode()
        + frame
        + b"\r\n"
    )


class SetupRequest(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class SessionRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class SyncRequest(BaseModel):
    full_scan: bool = Field(default=False, alias="fullScan")


class PointerPoint(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class DragRequest(BaseModel):
    points: list[PointerPoint] = Field(min_length=2, max_length=120)


class PointerRequest(BaseModel):
    action: Literal["down", "move", "up"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class KeyRequest(BaseModel):
    key: Literal[
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        "Backspace", "Enter", "Tab",
    ]


class AdminStore:
    """Small first-boot credential store; the database layer replaces this facade later."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @property
    def configured(self) -> bool:
        return self.path.is_file()

    def create(self, password_hash: str) -> None:
        if self.configured:
            raise FileExistsError(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"passwordHash": password_hash}, separators=(",", ":")),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.path)

    def password_hash(self) -> str | None:
        if not self.configured:
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        encoded = value.get("passwordHash") if isinstance(value, dict) else None
        return str(encoded) if encoded else None


def _prepare_directories(root: Path) -> None:
    for relative in ("data", "objects", "library", "tmp"):
        (root / relative).mkdir(parents=True, exist_ok=True)


def create_app(settings: Settings, *, auth_service=None, runtime_factory=None) -> FastAPI:
    cipher = CookieCipher(settings.master_key.get_secret_value())
    session_codec = SessionCodec(cipher)
    password_hasher = PasswordHasher()
    admin_store = AdminStore(settings.archive_root / "data" / "admin.json")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        _prepare_directories(settings.archive_root)
        owned_database = Database(settings.archive_root / "data" / "archive.sqlite3")
        await owned_database.open()
        library_repository = LibraryRepository(owned_database)
        await library_repository.backfill_legacy_collections()
        await library_repository.ensure_account_sources()
        application.state.database = owned_database
        application.state.archive_repository = ArchiveRepository(owned_database)
        application.state.library_repository = library_repository
        application.state.job_repository = JobRepository(owned_database)
        browser_coordinator = BrowserCoordinator(BrowserProfileStore(settings.archive_root))
        application.state.browser_coordinator = browser_coordinator
        owns_auth_service = auth_service is None
        if auth_service is None:
            from .auth_browser import AuthBrowser
            from .auth_service import AuthService

            application.state.auth_service = AuthService(
                owned_database,
                cipher,
                AuthBrowser(browser_coordinator),
            )
        else:
            application.state.auth_service = auth_service
        runtime = (
            runtime_factory(
                settings,
                owned_database,
                application.state.auth_service,
                browser_coordinator,
            )
            if runtime_factory is not None
            else None
        )
        application.state.runtime = runtime
        if runtime is not None:
            await runtime.start()
        try:
            yield
        finally:
            if runtime is not None:
                await runtime.stop()
            if owns_auth_service:
                await application.state.auth_service.close()
            await browser_coordinator.close()
            await owned_database.close()

    app = FastAPI(title="Yingcang", lifespan=lifespan)
    app.state.settings = settings
    app.state.admin_store = admin_store

    def decode_session(request: Request) -> bool:
        return session_codec.is_valid(request.cookies.get(SESSION_COOKIE))

    def issue_session(response: Response) -> None:
        csrf_token = secrets.token_urlsafe(32)
        session = cipher.encrypt(
            {
                "sub": "admin",
                "expiresAt": int(time.time()) + settings.session_ttl_seconds,
            }
        ).decode("ascii")
        response.set_cookie(
            SESSION_COOKIE,
            session,
            httponly=True,
            samesite="strict",
            secure=settings.secure_cookies,
            max_age=settings.session_ttl_seconds,
        )
        response.set_cookie(
            CSRF_COOKIE,
            csrf_token,
            httponly=False,
            samesite="strict",
            secure=settings.secure_cookies,
            max_age=settings.session_ttl_seconds,
        )

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        is_mutation = request.method not in SAFE_METHODS
        is_api = request.url.path.startswith("/api/")
        setup_path = request.url.path == "/api/setup"
        status_path = request.url.path == "/api/status"
        login_path = request.url.path == "/api/session" and request.method == "POST"
        protected = (
            is_api
            and admin_store.configured
            and not setup_path
            and not status_path
            and not login_path
        )
        session_valid = decode_session(request)
        if protected and not session_valid:
            return JSONResponse(
                status_code=401,
                content={"code": "AUTH_REQUIRED", "message": "需要本地管理员登录"},
            )
        if is_mutation and protected:
            csrf_cookie = request.cookies.get(CSRF_COOKIE)
            csrf_header = request.headers.get("X-CSRF-Token")
            if not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_header or ""):
                return JSONResponse(
                    status_code=403,
                    content={
                        "code": "CSRF_REQUIRED",
                        "message": "缺少或无效的 CSRF 令牌",
                    },
                )
        return await call_next(request)

    @app.get("/health/live")
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready")
    async def readiness(request: Request) -> dict[str, object]:
        try:
            _prepare_directories(settings.archive_root)
            probe = settings.archive_root / "tmp" / ".write-probe"
            probe.write_bytes(b"ok")
            probe.unlink()
            archive_status = "ok"
        except OSError:
            archive_status = "error"
        try:
            request.app.state.browser_coordinator.profile_store.prepare()
            browser_profile_status = "ok"
        except OSError:
            browser_profile_status = "error"
        status = (
            "ok"
            if archive_status == "ok" and browser_profile_status == "ok"
            else "error"
        )
        return {
            "status": status,
            "checks": {
                "archiveRoot": archive_status,
                "browserProfile": browser_profile_status,
            },
        }

    @app.post("/api/setup", status_code=201)
    async def setup(payload: SetupRequest, response: Response) -> dict[str, bool]:
        try:
            admin_store.create(password_hasher.hash(payload.password))
        except FileExistsError:
            return JSONResponse(
                status_code=409,
                content={"code": "ALREADY_CONFIGURED", "message": "管理员已配置"},
            )

        issue_session(response)
        return {"configured": True}

    @app.get("/api/status")
    async def public_status(request: Request) -> dict[str, bool]:
        douyin = await request.app.state.database.fetchone(
            "SELECT 1 FROM auth_sessions "
            "WHERE provider='douyin' AND status='authenticated'"
        )
        return {
            "configured": admin_store.configured,
            "authenticated": decode_session(request),
            "douyinAuthenticated": douyin is not None,
        }

    @app.post("/api/session")
    async def login(payload: SessionRequest, response: Response):
        encoded = admin_store.password_hash()
        if encoded is None or not password_hasher.verify(encoded, payload.password):
            return JSONResponse(
                status_code=401,
                content={"code": "INVALID_CREDENTIALS", "message": "密码不正确"},
            )
        issue_session(response)
        return {"authenticated": True}

    @app.delete("/api/session")
    async def logout(response: Response) -> dict[str, bool]:
        response.delete_cookie(SESSION_COOKIE)
        response.delete_cookie(CSRF_COOKIE)
        return {"authenticated": False}

    @app.post("/api/protected-test")
    async def protected_test() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/sync", status_code=202)
    async def trigger_sync(payload: SyncRequest, request: Request):
        runtime = request.app.state.runtime
        if runtime is None:
            return JSONResponse(
                status_code=503,
                content={"code": "RUNTIME_UNAVAILABLE", "message": "同步服务未启动"},
            )
        run_id = await runtime.trigger_sync(full_scan=payload.full_scan)
        return {"runId": run_id}

    @app.post("/api/douyin/login", status_code=201)
    async def begin_douyin_login(request: Request) -> dict[str, object]:
        status = await request.app.state.auth_service.begin_login()
        return status.as_public_dict()

    @app.websocket("/ws/douyin/login/{login_id}")
    async def douyin_login_socket(websocket: WebSocket, login_id: str) -> None:
        await handle_browser_socket(
            websocket,
            login_id,
            auth_service=websocket.app.state.auth_service,
            session_codec=session_codec,
            session_cookie=SESSION_COOKIE,
        )

    @app.get("/api/douyin/login/{login_id}")
    async def douyin_login_status(login_id: str, request: Request):
        try:
            status = await request.app.state.auth_service.get_status(
                login_id,
                refresh_screenshot=False,
            )
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"code": "LOGIN_NOT_FOUND", "message": "登录会话不存在"},
            )
        return status.as_public_dict()

    @app.get("/api/douyin/login/{login_id}/stream.mjpeg")
    async def douyin_login_stream(login_id: str, request: Request):
        service = request.app.state.auth_service
        try:
            first_frame = await service.frame(login_id)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"code": "LOGIN_NOT_FOUND", "message": "登录会话不存在"},
            )
        except ValueError:
            return JSONResponse(
                status_code=409,
                content={"code": "LOGIN_NOT_INTERACTIVE", "message": "登录画面已不可操作"},
            )

        async def frames():
            frame = first_frame
            while True:
                yield _mjpeg_chunk(frame)
                await asyncio.sleep(MJPEG_FRAME_INTERVAL_SECONDS)
                try:
                    frame = await service.frame(login_id)
                except (KeyError, ValueError):
                    return

        return StreamingResponse(
            frames(),
            media_type=f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/api/douyin/login/{login_id}/qr.png")
    async def douyin_login_qr(login_id: str, request: Request):
        try:
            status = await request.app.state.auth_service.get_status(login_id)
        except KeyError:
            status = None
        if status is None or status.screenshot_png is None:
            return JSONResponse(
                status_code=404,
                content={"code": "QR_NOT_AVAILABLE", "message": "二维码不可用"},
            )
        return Response(
            content=status.screenshot_png,
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/api/douyin/login/{login_id}/cancel")
    async def cancel_douyin_login(login_id: str, request: Request):
        try:
            status = await request.app.state.auth_service.cancel(login_id)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"code": "LOGIN_NOT_FOUND", "message": "登录会话不存在"},
            )
        return status.as_public_dict()

    @app.post("/api/douyin/login/{login_id}/drag")
    async def drag_douyin_login(
        login_id: str, payload: DragRequest, request: Request
    ):
        points = [(point.x, point.y) for point in payload.points]
        try:
            status = await request.app.state.auth_service.drag(login_id, points)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"code": "LOGIN_NOT_FOUND", "message": "登录会话不存在"},
            )
        except ValueError:
            return JSONResponse(
                status_code=409,
                content={"code": "LOGIN_NOT_INTERACTIVE", "message": "登录画面已不可操作"},
            )
        return status.as_public_dict()

    @app.post("/api/douyin/login/{login_id}/pointer", status_code=202)
    async def pointer_douyin_login(
        login_id: str, payload: PointerRequest, request: Request
    ):
        try:
            await request.app.state.auth_service.pointer(
                login_id, payload.action, payload.x, payload.y
            )
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"code": "LOGIN_NOT_FOUND", "message": "登录会话不存在"},
            )
        except ValueError:
            return JSONResponse(
                status_code=409,
                content={"code": "LOGIN_NOT_INTERACTIVE", "message": "登录画面已不可操作"},
            )
        return {"accepted": True}

    @app.post("/api/douyin/login/{login_id}/key", status_code=202)
    async def key_douyin_login(
        login_id: str, payload: KeyRequest, request: Request
    ):
        try:
            await request.app.state.auth_service.key(login_id, payload.key)
        except KeyError:
            return JSONResponse(
                status_code=404,
                content={"code": "LOGIN_NOT_FOUND", "message": "登录会话不存在"},
            )
        except ValueError:
            return JSONResponse(
                status_code=409,
                content={"code": "LOGIN_NOT_INTERACTIVE", "message": "登录画面已不可操作"},
            )
        return {"accepted": True}

    from .routes.archive import router as archive_router
    from .routes.creators import router as creators_router
    from .routes.feed import router as feed_router
    from .routes.jobs import router as jobs_router
    from .routes.library import router as library_router
    from .routes.media import router as media_router

    app.include_router(archive_router)
    app.include_router(creators_router)
    app.include_router(feed_router)
    app.include_router(jobs_router)
    app.include_router(library_router)
    app.include_router(media_router)

    if settings.web_dist is not None and (settings.web_dist / "index.html").is_file():
        assets = settings.web_dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="web-assets")

        @app.get("/{spa_path:path}", include_in_schema=False)
        async def spa(spa_path: str):
            if spa_path.startswith(("api/", "health/")):
                return JSONResponse(status_code=404, content={"code": "NOT_FOUND"})
            return FileResponse(settings.web_dist / "index.html")

    return app
