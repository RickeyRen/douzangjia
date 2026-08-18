from fastapi import APIRouter, Query, Request

from ..download_monitor import DownloadMonitor

router = APIRouter(prefix="/api")


@router.get("/jobs")
async def jobs(request: Request, limit: int = Query(default=50, ge=1, le=200)):
    return await DownloadMonitor(request.app.state.database).snapshot(limit=limit)


@router.get("/sync/runs")
async def sync_runs(request: Request, limit: int = Query(default=20, ge=1, le=100)):
    rows = await request.app.state.database.fetchall(
        "SELECT id, mode, phase, status, discovered_count, enqueued_count, "
        "error_code, started_at, finished_at FROM sync_runs "
        "ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    return {
        "items": [
            {
                "id": row["id"],
                "mode": row["mode"],
                "phase": row["phase"],
                "status": row["status"],
                "discovered": row["discovered_count"],
                "enqueued": row["enqueued_count"],
                "errorCode": row["error_code"],
                "startedAt": row["started_at"],
                "finishedAt": row["finished_at"],
            }
            for row in rows
        ]
    }
