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
- The authenticated production shell was inspected in Chrome at 1200×699 and 430×932. Both layouts had `scrollWidth === clientWidth`; no critical value was clipped.
- At 1200×699, the dashboard content container correctly reduced four-column sections to two columns and five-column sections to three columns after accounting for the application rail.
- At 430×932, every visible button measured at least 44×44 CSS pixels, the bottom navigation remained visible, and the page had no horizontal overflow.
- The production dark/light theme control completed a round trip successfully. Console messages attributable to `http://192.168.0.6:8099` contained no errors or warnings; unrelated Chrome-extension messages were excluded.
- Production source progress used the remote source total when it exceeded the locally discovered count, including `✈️` at 67.2% and `想去的地方` at 95.8% during acceptance.

## Issues

- P2 fixed: a non-zero archive share smaller than 0.1% was rounded to `0%`; it now displays `<0.1%`.
- Expected data state: the Douyin unique ID is currently absent in the remote account record, so the UI truthfully displays “暂未获取”.
- Expected QA limitation: the isolated render process cannot observe the production worker and Chromium process objects, so its Runtime preview shows those two components as unavailable. Production values come from the in-process runtime contract and are covered by backend/API tests.
- Browser-extension warnings observed during Chrome acceptance originated from extension URLs and did not come from the Douzangjia application.

final result: pass
