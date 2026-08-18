import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import Settings
from .security import CookieCipher, PasswordHasher

SESSION_COOKIE = "archive_session"
CSRF_COOKIE = "archive_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT_PATHS = {"/api/setup", "/api/session"}


class SetupRequest(BaseModel):
    password: str = Field(min_length=12, max_length=256)


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


def _prepare_directories(root: Path) -> None:
    for relative in ("data", "objects", "library", "tmp"):
        (root / relative).mkdir(parents=True, exist_ok=True)


def create_app(settings: Settings) -> FastAPI:
    cipher = CookieCipher(settings.master_key.get_secret_value())
    password_hasher = PasswordHasher()
    admin_store = AdminStore(settings.archive_root / "data" / "admin.json")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        _prepare_directories(settings.archive_root)
        yield

    app = FastAPI(title="Douyin NAS Archive", lifespan=lifespan)
    app.state.settings = settings
    app.state.admin_store = admin_store

    @app.middleware("http")
    async def csrf_guard(request: Request, call_next):
        is_mutation = request.method not in SAFE_METHODS
        is_api = request.url.path.startswith("/api/")
        if is_mutation and is_api and request.url.path not in CSRF_EXEMPT_PATHS:
            session_token = request.cookies.get(SESSION_COOKIE)
            if session_token:
                try:
                    session = cipher.decrypt(session_token)
                    session_valid = session.get("expiresAt", 0) > int(time.time())
                except (ValueError, AttributeError):
                    session_valid = False
                if session_valid:
                    csrf_cookie = request.cookies.get(CSRF_COOKIE)
                    csrf_header = request.headers.get("X-CSRF-Token")
                    if not csrf_cookie or not secrets.compare_digest(
                        csrf_cookie, csrf_header or ""
                    ):
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
    async def readiness() -> dict[str, object]:
        try:
            _prepare_directories(settings.archive_root)
            probe = settings.archive_root / "tmp" / ".write-probe"
            probe.write_bytes(b"ok")
            probe.unlink()
            archive_status = "ok"
            status = "ok"
        except OSError:
            archive_status = "error"
            status = "error"
        return {"status": status, "checks": {"archiveRoot": archive_status}}

    @app.post("/api/setup", status_code=201)
    async def setup(payload: SetupRequest, response: Response) -> dict[str, bool]:
        try:
            admin_store.create(password_hasher.hash(payload.password))
        except FileExistsError:
            return JSONResponse(
                status_code=409,
                content={"code": "ALREADY_CONFIGURED", "message": "管理员已配置"},
            )

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
        return {"configured": True}

    @app.post("/api/protected-test")
    async def protected_test() -> dict[str, bool]:
        return {"ok": True}

    return app
