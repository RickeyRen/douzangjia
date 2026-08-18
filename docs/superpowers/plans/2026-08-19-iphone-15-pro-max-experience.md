# iPhone 15 Pro Max Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a complete, touch-native 留影 browsing and management experience at the iPhone 15 Pro Max `430 × 932` viewport without regressing desktop behavior.

**Architecture:** Keep one shared feed and API data flow. Add focused mobile navigation, sheet, media-control, and item-detail components around it; consume the existing cursor API for incremental loading and poll utility data only while its sheet is mounted.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind CSS v4, Vitest, Testing Library, Phosphor Icons, FastAPI, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-19-iphone-15-pro-max-experience-design.md`

## Global Constraints

- Primary viewport is exactly `430 × 932` CSS pixels with touch enabled and device scale factor 3.
- Preserve the existing desktop collection rail and desktop detail sidebar.
- Do not add a new frontend dependency.
- Use only the existing off-black palette, coral accent, Geist/SF/PingFang typography, and `@phosphor-icons/react` icons.
- All mobile interactive targets are at least `44 × 44` CSS pixels and respect top and bottom safe-area insets.
- Tests precede production changes and each new behavior is observed failing before implementation.
- No browser-session material, cookies, local database, build output, or secrets enter git.

---

### Task 1: Mobile Navigation And Reachable Utility Surfaces

**Files:**
- Create: `web/src/features/navigation/MobileNavigation.tsx`
- Modify: `web/src/features/navigation/CollectionRail.tsx`
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`
- Test: `web/src/features/feed/FeedPage.test.tsx`

**Interfaces:**
- Consumes: `Collection[]`, `selected?: string`, `UtilityPanel` from the current navigation layer.
- Produces: `MobileDestination = "feed" | "collections" | "search" | "activity" | "settings"` and callbacks `onOpen(destination)`.

- [ ] **Step 1: Write the failing mobile-navigation test**

```tsx
it("keeps collections, search, activity, and settings reachable on mobile", async () => {
  const user = userEvent.setup();
  render(<FeedPage />);
  const navigation = await screen.findByRole("navigation", { name: "移动导航" });
  expect(within(navigation).getByRole("button", { name: "收藏夹" })).toBeVisible();
  expect(within(navigation).getByRole("button", { name: "搜索" })).toBeVisible();
  await user.click(within(navigation).getByRole("button", { name: "活动" }));
  expect(await screen.findByRole("dialog", { name: "活动" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "关闭面板" }));
  await user.click(within(navigation).getByRole("button", { name: "设置" }));
  expect(await screen.findByRole("dialog", { name: "设置" })).toBeVisible();
});
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run: `npm test -- FeedPage.test.tsx -t "keeps collections"`

Expected: FAIL because no navigation named `移动导航` exists.

- [ ] **Step 3: Implement the focused mobile navigation**

Create a fixed, safe-area-aware bottom navigation with five labelled Phosphor-icon buttons. Add `activity` to `UtilityPanel` and route mobile destinations to the existing collection drawer, a new search sheet state, `ArchiveStatusPanel`, or feed close/reset behavior. Keep `CollectionRail` unchanged above the mobile breakpoint.

- [ ] **Step 4: Run the targeted test and verify GREEN**

Run: `npm test -- FeedPage.test.tsx -t "keeps collections"`

Expected: PASS with no React act warnings.

### Task 2: Cursor Pagination Beyond The First Twenty Items

**Files:**
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/styles/app.css`
- Test: `web/src/features/feed/FeedPage.test.tsx`

**Interfaces:**
- Consumes: existing `fetchFeed({ collectionId, search, cursor })` and `nextCursor`.
- Produces: appended, de-duplicated `FeedItem[]`, `loadingMore`, `loadMoreError`, and a pagination sentinel.

- [ ] **Step 1: Write the failing pagination test**

```tsx
it("loads and appends the next cursor page without duplicates", async () => {
  vi.mocked(api.fetchFeed)
    .mockResolvedValueOnce({ items: [itemFor(collections[0])], nextCursor: "page-2" })
    .mockResolvedValueOnce({ items: [itemFor(collections[0]), itemFor(collections[1])], nextCursor: null });
  render(<FeedPage />);
  await screen.findByText("来自 想去的地方");
  await userEvent.click(screen.getByRole("button", { name: "加载更多" }));
  expect(await screen.findByText("来自 好看的美女")).toBeVisible();
  expect(screen.getAllByText("来自 想去的地方")).toHaveLength(1);
  expect(api.fetchFeed).toHaveBeenLastCalledWith(expect.objectContaining({ cursor: "page-2" }));
});
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run: `npm test -- FeedPage.test.tsx -t "loads and appends"`

Expected: FAIL because the first-page result discards `nextCursor` and no load-more control exists.

- [ ] **Step 3: Implement pagination and recovery**

Store `nextCursor`, append with a `Set` keyed by `awemeId`, preserve loaded cards on a page error, and expose an accessible `加载更多` control that doubles as an IntersectionObserver sentinel. Reset the cursor and items when collection or deferred search changes. Ensure stale requests cannot append after a filter change.

- [ ] **Step 4: Run the targeted test and verify GREEN**

Run: `npm test -- FeedPage.test.tsx -t "loads and appends"`

Expected: PASS; first and second API calls contain the correct cursor state.

### Task 3: Mobile Search Surface

**Files:**
- Create: `web/src/features/feed/MobileSearchSheet.tsx`
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`
- Test: `web/src/features/feed/FeedPage.test.tsx`

**Interfaces:**
- Consumes: `value: string`, `onChange(value: string)`, and `onClose()`.
- Produces: labelled dialog with autofocus input, clear button, close button, and current result state text.

- [ ] **Step 1: Write the failing search-sheet test**

```tsx
it("opens a labelled mobile search and applies then clears its query", async () => {
  const user = userEvent.setup();
  render(<FeedPage />);
  await user.click(await screen.findByRole("button", { name: "搜索" }));
  const dialog = screen.getByRole("dialog", { name: "搜索归档" });
  const input = within(dialog).getByRole("searchbox", { name: "搜索归档" });
  await user.type(input, "旅行家");
  await waitFor(() => expect(api.fetchFeed).toHaveBeenLastCalledWith(expect.objectContaining({ search: "旅行家" })));
  await user.click(within(dialog).getByRole("button", { name: "清除搜索" }));
  expect(input).toHaveValue("");
});
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run: `npm test -- FeedPage.test.tsx -t "opens a labelled mobile search"`

Expected: FAIL because the current mobile search icon has no usable input surface.

- [ ] **Step 3: Implement the search sheet**

Use a semantic dialog with a sticky labelled search field, 44-pixel clear and close controls, safe-area padding, and the existing deferred search state. Do not duplicate feed results inside the sheet; closing it returns to the filtered feed.

- [ ] **Step 4: Run the targeted test and verify GREEN**

Run: `npm test -- FeedPage.test.tsx -t "opens a labelled mobile search"`

Expected: PASS and the focused input has an accessible name.

### Task 4: Touch-Native Video Controls And Item Details

**Files:**
- Create: `web/src/features/feed/ItemDetailsSheet.tsx`
- Modify: `web/src/features/feed/FeedCard.tsx`
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`
- Test: `web/src/features/feed/FeedCard.test.tsx`

**Interfaces:**
- Consumes: `FeedItem`, `active`, and optional `onOpenDetails(item)`.
- Produces: real play/pause, mute/unmute, and information buttons plus a `progress` element representing current time and duration.

- [ ] **Step 1: Write the failing media-control test**

```tsx
it("pauses, resumes, unmutes, and opens details with touch controls", async () => {
  const user = userEvent.setup();
  const play = vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => undefined);
  render(<FeedCard item={itemFor(collections[0])} active onOpenDetails={vi.fn()} />);
  await user.click(screen.getByRole("button", { name: "暂停视频" }));
  expect(pause).toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "播放视频" }));
  expect(play).toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "打开声音" }));
  expect(screen.getByRole("button", { name: "静音" })).toBeVisible();
});
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run: `npm test -- FeedCard.test.tsx`

Expected: FAIL because the video has no exposed controls.

- [ ] **Step 3: Implement media controls and details sheet**

Keep playback state local to `FeedCard`, use a ref for the `<video>`, pause inactive cards in a cleanup-safe effect, update progress from `timeupdate`/`loadedmetadata`, and keep gallery horizontal gestures untouched. Replace decorative action containers with labelled buttons; connect information to `ItemDetailsSheet` and collection to the collection drawer.

- [ ] **Step 4: Run the targeted test and verify GREEN**

Run: `npm test -- FeedCard.test.tsx`

Expected: PASS with `play` and `pause` restored after each test.

### Task 5: Live Activity And Mobile Settings Sheets

**Files:**
- Modify: `web/src/features/status/ArchiveStatusPanel.tsx`
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`
- Test: `web/src/features/status/ArchiveStatusPanel.test.tsx`

**Interfaces:**
- Consumes: `kind: "downloads" | "sync" | "activity" | "settings"`, existing jobs/runs/status API calls.
- Produces: semantic dialog, activity tabs, refresh-on-mount, 5-second polling only while activity/download/sync is mounted, and full-sync state feedback.

- [ ] **Step 1: Write the failing polling-cleanup test**

```tsx
it("refreshes activity while open and stops after unmount", async () => {
  vi.useFakeTimers();
  const view = render(<ArchiveStatusPanel kind="activity" onClose={vi.fn()} />);
  await vi.waitFor(() => expect(api.fetchJobs).toHaveBeenCalledTimes(1));
  await vi.advanceTimersByTimeAsync(5_000);
  expect(api.fetchJobs).toHaveBeenCalledTimes(2);
  view.unmount();
  await vi.advanceTimersByTimeAsync(5_000);
  expect(api.fetchJobs).toHaveBeenCalledTimes(2);
  vi.useRealTimers();
});
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run: `npm test -- ArchiveStatusPanel.test.tsx`

Expected: FAIL because `activity` and interval refresh do not exist.

- [ ] **Step 3: Implement activity tabs, polling, and dialog semantics**

Fetch jobs and runs in parallel for activity, use a single cleaned-up interval, use functional state replacement, keep manual full sync in the sync tab, and add `role="dialog"`, `aria-modal="true"`, and the existing title as the accessible name. Settings does not poll.

- [ ] **Step 4: Run the targeted test and verify GREEN**

Run: `npm test -- ArchiveStatusPanel.test.tsx`

Expected: PASS with no outstanding fake timers or act warnings.

### Task 6: Responsive Polish, Regression Suite, And Rendered QA

**Files:**
- Modify: `web/src/styles/app.css`
- Modify: `web/index.html`
- Test: all frontend tests and existing backend tests
- Temporary artifact: outside the repository, an iPhone screenshot and console/overflow report

**Interfaces:**
- Consumes: completed mobile components and the running Vite/FastAPI app.
- Produces: verified safe areas, no horizontal overflow, correct touch targets, and desktop regression evidence.

- [ ] **Step 1: Add the failing iPhone structure regression**

```tsx
it("exposes stable safe-area structure for the iphone viewport", async () => {
  render(<FeedPage />);
  const feed = await screen.findByTestId("archive-feed-root");
  expect(feed).toHaveClass("iphone-feed-shell");
  const navigation = screen.getByRole("navigation", { name: "移动导航" });
  expect(navigation).toHaveClass("iphone-bottom-nav");
  expect(within(navigation).getAllByRole("button").every((button) => button.classList.contains("touch-target"))).toBe(true);
});
```

- [ ] **Step 2: Run the focused structural test and verify RED**

Run: `npm test -- FeedPage.test.tsx -t "iphone viewport structure"`

Expected: FAIL because the stable safe-area/mobile-layout hooks are absent.

- [ ] **Step 3: Implement final mobile CSS**

Use `100dvh`, safe-area padding, `touch-action: pan-y` for the vertical feed, `touch-action: pan-x` for galleries, fixed bottom navigation with inner border and inner shadow, 44-pixel targets, visible `:focus-visible`, landscape compaction, and reduced-motion overrides. Do not animate layout dimensions.

- [ ] **Step 4: Run fresh automated verification**

Run:

```bash
cd web && npm test && npm run lint && npm run build
cd .. && .venv/bin/python -m pytest
```

Expected: all tests pass, ESLint reports no errors, Vite build exits 0, and pytest exits 0.

- [ ] **Step 5: Validate rendered behavior with the Browser path first**

Target flow: `/` -> browse feed -> load next page -> collections -> search -> video controls -> information -> activity -> settings.

Check `430 × 932`, `393 × 852`, `932 × 430`, and `1440 × 1000`; record page identity, meaningful DOM, no framework overlay, console errors/warnings, screenshot evidence, interaction state changes, `scrollWidth <= clientWidth`, and visible 44-pixel controls. If the in-app Browser invocation remains blocked, record the exact blocker and use the approved Playwright mobile-emulation fallback.

### Task 7: NAS Deployment, Online Reverification, And Checkpoint

**Files:**
- Modify on NAS: `/vol3/1000/docker/douyin-nas-archive` through the existing deployment workflow
- Git: current `codex/persistent-browser` branch

**Interfaces:**
- Consumes: verified working tree, existing Docker Compose deployment, approved NAS SSH key.
- Produces: healthy online service, current mobile bundle, critical flow evidence, and a recoverable checkpoint commit.

- [ ] **Step 1: Review release diff and excluded material**

Run `git status --short`, `git diff --check`, `git diff --stat`, inspect `git remote -v`, and verify that no profile, cookie, database, `.env`, media, build output, screenshot, or secret is tracked.

- [ ] **Step 2: Deploy with the existing non-destructive compose workflow**

Copy only source/configuration required by the deployment, rebuild the archive image, and recreate the service without deleting the archive root or persistent Chromium profile.

- [ ] **Step 3: Verify online health and archive behavior**

Check container health, `/health/live`, `/health/ready`, authenticated `/api/status`, collection/feed API results, media byte-range response, latest sync state, and current download worker progress. Repeat the critical `430 × 932` rendered interaction flow against `http://192.168.0.6:8099/`.

- [ ] **Step 4: Create the local checkpoint commit**

Run all final verification immediately before commit, then commit the reviewed source and tests with `feat: complete iphone archive experience` and create a dated checkpoint tag. Push the branch and new tag only if `git remote -v` confirms an approved private GitLab; otherwise preserve the local checkpoint and report that no approved remote is configured.
