from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ..settings_store import RuntimeSettings, SettingsStore

router = APIRouter(prefix="/api")

EDITABLE = set(RuntimeSettings.model_fields)


def _store(request: Request) -> SettingsStore:
    return request.app.state.settings_store


async def _payload(request: Request, values: RuntimeSettings) -> dict[str, Any]:
    store = _store(request)
    return {
        "values": values.model_dump(),
        "defaults": store.defaults.model_dump(),
        "overridden": sorted(await store.overrides()),
    }


@router.get("/settings")
async def read_settings(request: Request) -> dict[str, Any]:
    return await _payload(request, await _store(request).load())


@router.put("/settings")
async def write_settings(request: Request):
    body = await request.json()
    if not isinstance(body, dict) or not body:
        return JSONResponse(status_code=400, content={"code": "INVALID_SETTINGS", "message": "没有要修改的设置"})
    unknown = sorted(set(body) - EDITABLE)
    if unknown:
        return JSONResponse(
            status_code=400,
            content={"code": "UNKNOWN_SETTING", "message": f"未知设置项：{', '.join(unknown)}"},
        )
    try:
        values = await _store(request).update(body)
    except ValidationError as error:
        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        return JSONResponse(
            status_code=400,
            content={"code": "INVALID_SETTINGS", "message": f"{field}: {first['msg']}"},
        )
    runtime = request.app.state.runtime
    if runtime is not None and hasattr(runtime, "apply_settings"):
        await runtime.apply_settings(values)
    return await _payload(request, values)
