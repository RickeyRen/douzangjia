from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request

from ..review import CollectionReview

router = APIRouter(prefix="/api")


@router.get("/review")
async def get_review(request: Request):
    review = CollectionReview(request.app.state.database)
    snapshot = await review.snapshot()
    if snapshot is not None:
        return snapshot
    # First visit before the background job ran: start it, the page polls.
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is not None and hasattr(runtime, "build_review_soon"):
        runtime.build_review_soon()
    else:
        state = request.app.state
        if getattr(state, "review_task", None) is None or state.review_task.done():
            state.review_task = asyncio.create_task(review.rebuild())
    return {"state": "building"}
