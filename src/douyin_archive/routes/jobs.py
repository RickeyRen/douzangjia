from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api")


@router.get("/jobs")
async def jobs(request: Request, limit: int = Query(default=50, ge=1, le=200)):
    rows = await request.app.state.database.fetchall(
        "SELECT id, kind, remote_id, status, attempts, next_attempt_at, "
        "last_error_code, updated_at FROM download_jobs ORDER BY updated_at DESC LIMIT ?",
        (limit,),
    )
    return {
        "items": [
            {
                "id": row["id"],
                "kind": row["kind"],
                "remoteId": row["remote_id"],
                "status": row["status"],
                "attempts": row["attempts"],
                "nextAttemptAt": row["next_attempt_at"],
                "errorCode": row["last_error_code"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]
    }


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
