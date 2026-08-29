# Douzangjia Real Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Remnawave-quality Douzangjia dashboard whose throughput, runtime, queue, NAS, library, account, trend, and source-progress values all come from real backend data.

**Architecture:** Extend the existing dashboard snapshot instead of adding a second polling system. Python/SQLite own truthful aggregation and runtime observation; React owns scan-first layout and stale-but-visible live state; lightweight SVG owns only trend geometry.

**Tech Stack:** Python 3.12, FastAPI, SQLite, React, TypeScript, Vite, Vitest, Testing Library, CSS, Phosphor Icons

**Spec:** `docs/superpowers/specs/2026-08-29-douzangjia-real-dashboard.md`

## Global Constraints

- Do not fabricate a metric, comparison, process boundary, account value, or completion total.
- Preserve the persistent Chromium profile, application authentication, SQLite database, archive content, and existing SSE endpoint.
- Keep Simplified Chinese and English translations in sync.
- Use the existing React/Vite application and Phosphor icon family; add no chart dependency.
- Treat 430×932 mobile portrait as a sibling layout and keep all essential values available without hover.

---

### Task 1: Truthful throughput and process observation

**Files:**
- Modify: `tests/test_dashboard_service.py`
- Modify: `tests/test_dashboard_api.py`
- Modify: `src/douyin_archive/telemetry.py`
- Modify: `src/douyin_archive/dashboard_service.py`

**Interfaces:**
- Produces: `process_tree_snapshot(root_pid: int | None = None) -> dict[str, int]`
- Produces: `DashboardSnapshot.throughput` with `today`, `sevenDays`, `thirtyDays`, `lifetime`, and comparison availability.

- [ ] **Step 1: Write failing process-tree and throughput tests**

```python
assert process_tree_snapshot(root_pid=fixture_root)["browserProcessCount"] == 2
assert snapshot["throughput"]["today"]["bytes"] == 300
assert snapshot["throughput"]["today"]["comparisonAvailable"] is True
```

- [ ] **Step 2: Run the focused tests and confirm missing-contract failures**

Run: `pytest tests/test_dashboard_service.py tests/test_dashboard_api.py -q`

- [ ] **Step 3: Implement `/proc` child traversal and Asia/Shanghai completion-window aggregation**

```python
return {
    "today": window(now_start, now, previous_start),
    "sevenDays": window(now - 7 * DAY, now, now - 14 * DAY),
    "thirtyDays": window(now - 30 * DAY, now, now - 60 * DAY),
    "lifetime": {"bytes": archive_bytes},
}
```

- [ ] **Step 4: Run focused tests until green**

Run: `pytest tests/test_dashboard_service.py tests/test_dashboard_api.py -q`

- [ ] **Step 5: Commit the backend aggregation checkpoint**

```bash
git add tests/test_dashboard_service.py tests/test_dashboard_api.py src/douyin_archive/telemetry.py src/douyin_archive/dashboard_service.py
git commit -m "feat: expose truthful dashboard throughput"
```

### Task 2: Real runtime service contract

**Files:**
- Modify: `tests/test_dashboard_service.py`
- Modify: `tests/test_dashboard_api.py`
- Modify: `tests/test_browser_coordinator.py`
- Modify: `src/douyin_archive/browser_coordinator.py`
- Modify: `src/douyin_archive/runtime.py`
- Modify: `src/douyin_archive/routes/dashboard.py`
- Modify: `src/douyin_archive/dashboard_service.py`

**Interfaces:**
- Produces: `BrowserCoordinator.runtime_state() -> dict[str, object]`
- Produces: `ArchiveRuntime.dashboard_runtime() -> dict[str, object]`
- Produces: `DashboardSnapshot.runtime.application/downloader/browser`.

- [ ] **Step 1: Write failing tests for browser started/busy state and runtime cards**

```python
assert payload["runtime"]["downloader"]["workerCount"] == 2
assert payload["runtime"]["browser"]["status"] in {"running", "busy", "unavailable"}
assert payload["runtime"]["application"]["memoryBytes"] >= 0
```

- [ ] **Step 2: Run focused tests and confirm the runtime object is absent**

Run: `pytest tests/test_browser_coordinator.py tests/test_dashboard_service.py tests/test_dashboard_api.py -q`

- [ ] **Step 3: Add public runtime observation without exposing mutable internals**

```python
def runtime_state(self) -> dict[str, object]:
    return {"started": self._context is not None, "busy": self._lease_lock.locked()}
```

- [ ] **Step 4: Compose application, downloader, and browser runtime values into `/api/dashboard`**

```python
runtime = await request.app.state.runtime.dashboard_runtime() if request.app.state.runtime else None
return await service.snapshot(runtime=runtime)
```

- [ ] **Step 5: Run focused tests until green and commit**

Run: `pytest tests/test_browser_coordinator.py tests/test_dashboard_service.py tests/test_dashboard_api.py -q`

### Task 3: Typed React dashboard primitives and formatting

**Files:**
- Modify: `web/src/app/api.ts`
- Create: `web/src/features/home/dashboardFormat.ts`
- Create: `web/src/features/home/dashboardFormat.test.ts`
- Create: `web/src/features/home/DashboardMetric.tsx`
- Create: `web/src/features/home/DashboardTrend.tsx`
- Create: `web/src/features/home/RuntimeSection.tsx`
- Create: `web/src/features/home/SourceProgressSection.tsx`

**Interfaces:**
- Consumes: backend `throughput` and `runtime` objects from Tasks 1–2.
- Produces: `formatDelta`, `formatUpdatedAt`, `DashboardMetric`, `DashboardTrend`, `RuntimeSection`, and `SourceProgressSection`.

- [ ] **Step 1: Write failing formatter and component-contract tests**

```ts
expect(formatDelta(1024, true)).toBe("+1.0 KB");
expect(formatDelta(0, false)).toBe("数据积累中");
```

- [ ] **Step 2: Run focused Vitest tests and confirm missing module failures**

Run: `cd web && npm test -- dashboardFormat.test.ts`

- [ ] **Step 3: Add exact TypeScript contracts and small memo-friendly components**

```ts
export type ThroughputWindow = {
  bytes: number;
  previousBytes: number;
  deltaBytes: number;
  comparisonAvailable: boolean;
};
```

- [ ] **Step 4: Run focused tests until green**

Run: `cd web && npm test -- dashboardFormat.test.ts`

### Task 4: Full Remnawave-style home composition

**Files:**
- Modify: `web/src/features/home/HomePage.test.tsx`
- Modify: `web/src/features/home/HomePage.tsx`
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`

**Interfaces:**
- Consumes: typed snapshot, existing shared SSE state, and Task 3 components.
- Produces: ten ordered dashboard regions with accessible headings and real-value labels.

- [ ] **Step 1: Replace the old broad test with failing user-visible section and value tests**

```ts
for (const name of ["归档引擎使用情况", "服务详情", "归档吞吐", "队列状态", "NAS 系统", "资料库", "抖音账号", "收藏分类进度", "Runtime"]) {
  expect(screen.getByRole("heading", { name })).toBeVisible();
}
expect(screen.getByText("sky-gap")).toBeVisible();
```

- [ ] **Step 2: Run HomePage tests and confirm expected missing headings**

Run: `cd web && npm test -- HomePage.test.tsx`

- [ ] **Step 3: Compose the complete home page from focused components**

```tsx
<DashboardSection title={t("engineUsageTitle")}>
  <DashboardMetricGrid metrics={engineMetrics} />
</DashboardSection>
```

- [ ] **Step 4: Add matching Simplified Chinese and English keys**

Run: `cd web && npm test -- i18n.test.ts HomePage.test.tsx`

- [ ] **Step 5: Verify category click and download-monitor navigation remain functional**

Run: `cd web && npm test -- HomePage.test.tsx`

### Task 5: Visual system and responsive sibling layouts

**Files:**
- Modify: `web/src/styles/tokens.css`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/features/home/HomeTypography.test.ts`

**Interfaces:**
- Consumes: accepted desktop/mobile concepts and Task 4 class names.
- Produces: dark operational dashboard at desktop, tablet, and 360–430px portrait widths.

- [ ] **Step 1: Add failing typography/token checks for the dashboard-specific rules**

```ts
expect(source).toContain(".home-dashboard-section");
expect(source).toContain("grid-template-columns: repeat(4");
expect(source).toContain("@media (max-width: 719px)");
```

- [ ] **Step 2: Run the typography test and confirm new contracts are absent**

Run: `cd web && npm test -- HomeTypography.test.ts`

- [ ] **Step 3: Implement the accepted token ledger and desktop layout**

- [ ] **Step 4: Implement the 430×932 sibling layout, safe areas, 44px controls, and no horizontal overflow**

- [ ] **Step 5: Run focused tests, lint, and build**

Run: `cd web && npm test -- HomeTypography.test.ts HomePage.test.tsx && npm run lint && npm run build`

### Task 6: End-to-end verification, design QA, and NAS delivery

**Files:**
- Create: `design-qa.md`
- Create: `docs/designs/douzangjia-dashboard-fidelity-ledger.md`

**Interfaces:**
- Consumes: accepted concepts and the fully rendered implementation.
- Produces: passing automated suite, visual comparison evidence, deployed NAS service, checkpoint commit, and tag.

- [ ] **Step 1: Run all backend and frontend verification**

Run: `pytest -q`

Run: `cd web && npm test && npm run lint && npm run build`

Run: `git diff --check`

- [ ] **Step 2: Deploy without replacing persistent data or login state**

Use the existing NAS deployment script/path and rebuild only application code/container layers.

- [ ] **Step 3: Verify authenticated `/api/dashboard`, SSE updates, desktop layout, current IAB viewport, and 430×932 layout**

- [ ] **Step 4: Compare concept and implementation screenshots with `view_image`, document at least five comparison points, and resolve every P0/P1/P2 issue**

- [ ] **Step 5: Write `design-qa.md` with `final result: passed` and remove temporary QA artifacts**

- [ ] **Step 6: Create the required local checkpoint commit and tag**

```bash
git add -A
git commit -m "feat: rebuild home as a real operations dashboard"
git tag checkpoint/douzangjia-real-dashboard-20260829
```

- [ ] **Step 7: Check for an approved private GitLab remote; push only if one exists and contains no secrets**

