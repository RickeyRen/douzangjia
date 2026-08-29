# Douzangjia Dashboard Design QA

## Scope

- Reference: Remnawave dashboard home
- Product: Douzangjia NAS dashboard
- Desktop: compact operational dashboard inside the existing collection rail
- Mobile: iPhone 15 Pro Max portrait, 430×932 CSS viewport
- Data rule: no fabricated metrics, comparisons, account identity, process boundary, or completion totals

## Verified evidence

- Backend aggregation tests cover Asia/Shanghai throughput windows, comparison availability, Linux process-tree memory, runtime state, dashboard API and SSE payloads.
- Frontend tests cover all ordered dashboard sections, real formatted values, stale-but-visible SSE state, source navigation, source auto-download policy, icon tones, typography and responsive grid contracts.
- Real NAS snapshot rendered 10,119 items, 4,094 ready media files, 6,822 creators, 15 sources, 5.1 GB archive data and 48 recent metric points.
- The NAS container image was rebuilt and `/health/ready` reported both `archiveRoot` and `browserProfile` as `ok`.
- Chromium profile remained persistent with mode `0700`.
- Desktop and 430×932 implementation screenshots are stored under `docs/designs/`.

## Issues

- P2 fixed: a non-zero archive share smaller than 0.1% was rounded to `0%`; it now displays `<0.1%`.
- Expected data state: the Douyin unique ID is currently absent in the remote account record, so the UI truthfully displays “暂未获取”.
- Expected QA limitation: the isolated render process cannot observe the production worker and Chromium process objects, so its Runtime preview shows those two components as unavailable. Production values come from the in-process runtime contract and are covered by backend/API tests.
- Remaining acceptance gate: authenticated production-shell screenshot and interaction check in the explicitly selected in-app browser.

final result: pending authenticated production-shell visual acceptance
