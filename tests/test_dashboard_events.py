from __future__ import annotations

import importlib

import pytest


async def test_event_bus_preserves_order_and_drops_stale_events_for_slow_clients() -> None:
    """Catches a dashboard subscriber growing unbounded memory."""
    module = importlib.import_module("douyin_archive.dashboard_events")
    bus = module.DashboardEventBus(queue_size=2)

    async with bus.subscribe() as queue:
        await bus.publish("metric", {"sequence": 1})
        await bus.publish("metric", {"sequence": 2})
        await bus.publish("metric", {"sequence": 3})
        first = await queue.get()
        second = await queue.get()

    assert first.data == {"sequence": 2}
    assert second.data == {"sequence": 3}
    assert bus.subscriber_count == 0


async def test_event_bus_rejects_sensitive_dashboard_payloads() -> None:
    """Catches cookies or signed media URLs leaking into browser events."""
    module = importlib.import_module("douyin_archive.dashboard_events")
    bus = module.DashboardEventBus()

    with pytest.raises(ValueError, match="sensitive"):
        await bus.publish("snapshot", {"nested": {"cookie": "secret"}})


def test_sse_frame_contains_retry_event_and_json_data() -> None:
    """Catches malformed frames that silently disable live reconnect."""
    module = importlib.import_module("douyin_archive.dashboard_events")

    frame = module.encode_sse(
        module.DashboardEvent("health", {"status": "healthy"})
    )

    assert frame == (
        "retry: 1500\n"
        "event: health\n"
        'data: {"status":"healthy"}\n\n'
    )


async def test_dashboard_stream_starts_with_a_real_snapshot() -> None:
    """Catches a newly connected home page waiting for the next periodic event."""
    module = importlib.import_module("douyin_archive.dashboard_events")
    bus = module.DashboardEventBus()

    async def load_snapshot() -> dict[str, object]:
        return {"generatedAt": 123, "queue": {"running": 1}}

    stream = module.dashboard_event_stream(load_snapshot, bus, refresh_seconds=60)
    try:
        first = await anext(stream)
    finally:
        await stream.aclose()

    assert "event: snapshot\n" in first
    assert 'data: {"generatedAt":123,"queue":{"running":1}}\n\n' in first
