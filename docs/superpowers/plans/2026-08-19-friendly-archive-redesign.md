# “留影”友好式全站 UI 重构实施计划（已废弃）

> 2026-08-19 用户否决了这一糖果式方向。仅作 Git 历史和取舍记录；有效计划为 `2026-08-19-cinematic-theme-redesign.md`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变归档、下载和抖音登录行为的前提下，将“留影”全站改为明亮、圆润、有实体按压反馈的友好式界面，并修复桌面端布局压缩和覆盖。

**Architecture:** 把视觉 token 和可复用物理控件收敛到 CSS，用流式 CSS Grid 替代桌面绝对定位，再逐个功能面替换暗色玻璃表面。React 数据和交互状态保持局部，不引入新状态或动画依赖。

**Tech Stack:** React, TypeScript, Vite, Tailwind CSS v4, `@phosphor-icons/react`, Vitest, Testing Library, Playwright CLI

**Spec:** `docs/superpowers/specs/2026-08-19-friendly-archive-redesign-design.md`

## Global Constraints

- 不使用任何外部品牌的商标、名称、角色、插画或资产。
- 不实现概念图中虚构的删除、分享、点赞、评论或存储数字。
- 不更改下载、数据库、认证加密和远程浏览器协议。
- 不新增 npm 依赖；继续使用 Phosphor 图标和 Tailwind v4。
- 新动效只能动画 `transform` 和 `opacity`，并支持 `prefers-reduced-motion`。
- 新增文案必须同时补齐中英文。
- 所有触摸目标至少 44x44px，图标按钮必须有可访问名称。
- 安全部署必须排除 `.env`、数据库、媒体归档、Chromium profile、cookie、缓存和构建产物。

---

## 文件结构

- Create `web/src/components/FriendlyIconButton.tsx`: 统一图标按钮、物理按压和可访问语义。
- Create `web/src/components/FriendlyButton.tsx`: 主要、次要和危险语义按钮。
- Create `web/src/features/feed/DesktopItemDetails.tsx`: 只负责大桌面流式详情栏。
- Modify `web/src/styles/tokens.css`: 白色/灰色/绿色 token 和物理尺寸。
- Modify `web/src/styles/app.css`: 全局物理控件、桌面网格、媒体舞台、移动安全区和状态样式。
- Modify `web/src/features/feed/FeedPage.tsx`: 流式应用外壳、顶部工具栏和桌面切换控件。
- Modify `web/src/features/feed/FeedCard.tsx`: 响应式媒体舞台和移动操作。
- Modify `web/src/features/navigation/CollectionRail.tsx`: 明亮桌面轨道。
- Modify `web/src/features/navigation/MobileNavigation.tsx`: 明亮底部导航和选中状态。
- Modify `web/src/features/feed/ItemDetailsSheet.tsx`, `MobileSearchSheet.tsx`, `GalleryViewer.tsx`: 明亮抽屉与媒体控件。
- Modify `web/src/features/status/ArchiveStatusPanel.tsx`, `DownloadMonitor.tsx`: 明亮任务/设置面板和真实进度状态。
- Modify `web/src/features/auth/LocalLoginPage.tsx`, `DouyinLoginPage.tsx`, `web/src/features/setup/SetupPage.tsx`, `web/src/app/App.tsx`: 全站引导、登录、加载和错误状态。
- Modify existing `*.test.tsx` files: 锁定真实布局语义和交互回归。

---

### Task 1: 设计 token 和物理控件

**Files:**
- Create: `web/src/components/FriendlyButton.tsx`
- Create: `web/src/components/FriendlyIconButton.tsx`
- Modify: `web/src/styles/tokens.css`
- Modify: `web/src/styles/app.css`
- Test: `web/src/components/FriendlyButton.test.tsx`

**Interfaces:**
- Produces: `FriendlyButton({ tone, fullWidth, children, ...buttonProps })`
- Produces: `FriendlyIconButton({ label, children, ...buttonProps })`
- Produces CSS classes: `friendly-button`, `friendly-icon-button`, `friendly-surface`, `friendly-panel`

- [ ] **Step 1: Write the failing behavior test**

```tsx
render(<FriendlyButton tone="primary">立即同步</FriendlyButton>);
expect(screen.getByRole("button", { name: "立即同步" })).toHaveClass("friendly-button", "friendly-button-primary");

render(<FriendlyIconButton label="关闭"><X /></FriendlyIconButton>);
expect(screen.getByRole("button", { name: "关闭" })).toHaveClass("friendly-icon-button");
```

- [ ] **Step 2: Verify RED**

Run: `cd web && npm test -- --run src/components/FriendlyButton.test.tsx`

Expected: FAIL because the components do not exist.

- [ ] **Step 3: Implement the two controls and tokens**

Use native `<button>`, preserve all React button attributes, and implement primary/secondary/danger tone classes. Define the exact colors, radii, 2px border, 4px solid lower edge, focus ring and active `translateY(3px)` from the spec.

- [ ] **Step 4: Verify GREEN**

Run: `cd web && npm test -- --run src/components/FriendlyButton.test.tsx && npm run lint`

Expected: test and ESLint pass.

- [ ] **Step 5: Commit checkpoint**

```bash
git add web/src/components web/src/styles
git commit -m "feat: add friendly archive design system"
```

### Task 2: 桌面流式网格和导航

**Files:**
- Create: `web/src/features/feed/DesktopItemDetails.tsx`
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/features/navigation/CollectionRail.tsx`
- Modify: `web/src/features/feed/FeedPage.test.tsx`

**Interfaces:**
- Produces: `DesktopItemDetails({ item }: { item: FeedItem })`
- Produces landmarks: `[data-testid="desktop-workspace"]`, `[data-testid="desktop-content"]`, `[data-testid="desktop-details"]`
- Consumes: `FriendlyIconButton`

- [ ] **Step 1: Add a failing desktop layout test**

```tsx
render(<FeedPage />);
const workspace = await screen.findByTestId("desktop-workspace");
expect(workspace).toHaveClass("archive-desktop-grid");
expect(screen.getByTestId("desktop-content")).toBeVisible();
expect(screen.getByTestId("desktop-details")).toBeVisible();
expect(screen.getByTestId("desktop-details")).not.toHaveClass("absolute");
```

The production mutation this catches is reintroducing an overlay sidebar or removing the central grid region.

- [ ] **Step 2: Verify RED**

Run: `cd web && npm test -- --run src/features/feed/FeedPage.test.tsx`

Expected: FAIL because the desktop workspace landmarks do not exist.

- [ ] **Step 3: Implement the flow layout**

Replace the root flex/absolute composition with `archive-desktop-grid`. Keep `FeedPage` data fetching and observers unchanged. Move current right-rail content into `DesktopItemDetails`; move previous/next buttons into a central flow footer; keep the header in normal flow.

- [ ] **Step 4: Restyle `CollectionRail`**

Use a white rail, readable charcoal labels, pale-green selected rows, real item counts, and the existing downloads/sync/settings actions. Do not add storage numbers or fake status.

- [ ] **Step 5: Verify GREEN and behavior regression**

Run: `cd web && npm test -- --run src/features/feed/FeedPage.test.tsx`

Expected: desktop structure, collection switching, panels, pagination and mobile reachability all pass.

- [ ] **Step 6: Commit checkpoint**

```bash
git add web/src/features/feed web/src/features/navigation
git commit -m "feat: rebuild desktop archive workspace"
```

### Task 3: 媒体舞台和 iPhone 响应式

**Files:**
- Modify: `web/src/features/feed/FeedCard.tsx`
- Modify: `web/src/features/feed/GalleryViewer.tsx`
- Modify: `web/src/features/navigation/MobileNavigation.tsx`
- Modify: `web/src/features/feed/FeedCard.test.tsx`
- Modify: `web/src/features/feed/FeedPage.test.tsx`
- Modify: `web/src/styles/app.css`

**Interfaces:**
- Preserves: video play/pause, mute, progress and gallery movement
- Produces: `.archive-media-stage`, `.archive-media-frame`, `.friendly-mobile-nav`

- [ ] **Step 1: Add failing tests for preserved media and mobile landmarks**

```tsx
expect(screen.getByTestId("feed-card-active")).toHaveClass("archive-media-stage");
expect(screen.getByRole("navigation", { name: "移动导航" })).toHaveClass("friendly-mobile-nav");
await user.click(screen.getByRole("button", { name: "暂停视频" }));
expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
```

- [ ] **Step 2: Verify RED**

Run: `cd web && npm test -- --run src/features/feed/FeedCard.test.tsx src/features/feed/FeedPage.test.tsx`

Expected: FAIL on missing friendly layout classes while playback assertions continue to characterize real behavior.

- [ ] **Step 3: Implement responsive media surfaces**

Desktop uses the grid's available height and width, a charcoal stage, a contained 9:16 media frame and no full-viewport card minimum. Mobile preserves one snap card per viewport, safe areas, caption readability and the three existing real media actions only.

- [ ] **Step 4: Implement mobile navigation**

Use a white solid surface, 2px top border, green selected feed state and 44px controls. Keep all five destinations and their callbacks.

- [ ] **Step 5: Verify GREEN**

Run: `cd web && npm test -- --run src/features/feed/FeedCard.test.tsx src/features/feed/FeedPage.test.tsx`

Expected: all media and navigation tests pass.

- [ ] **Step 6: Commit checkpoint**

```bash
git add web/src/features/feed web/src/features/navigation web/src/styles/app.css
git commit -m "feat: apply friendly media browsing surfaces"
```

### Task 4: 下载、同步、设置和抽屉

**Files:**
- Modify: `web/src/features/status/ArchiveStatusPanel.tsx`
- Modify: `web/src/features/status/DownloadMonitor.tsx`
- Modify: `web/src/features/feed/ItemDetailsSheet.tsx`
- Modify: `web/src/features/feed/MobileSearchSheet.tsx`
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/features/status/ArchiveStatusPanel.test.tsx`

**Interfaces:**
- Consumes: `FriendlyButton`, `FriendlyIconButton`
- Preserves: `DownloadSnapshot`, polling intervals, tabs, real sync trigger and all ARIA roles

- [ ] **Step 1: Add a failing light-panel behavior test**

```tsx
render(<ArchiveStatusPanel kind="activity" onClose={vi.fn()} />);
const dialog = await screen.findByRole("dialog", { name: "活动" });
expect(dialog).toHaveClass("friendly-drawer");
expect(within(screen.getByRole("region", { name: "下载队列" })).getByText("14.7 MB / 47.7 MB")).toBeVisible();
```

The test fails if visual refactoring replaces the real download component or removes its data contract.

- [ ] **Step 2: Verify RED**

Run: `cd web && npm test -- --run src/features/status/ArchiveStatusPanel.test.tsx`

Expected: FAIL on the new drawer class.

- [ ] **Step 3: Restyle panels without changing data flow**

Convert overlay, drawer, tab, status, settings and sync controls to the light system. Keep activity at 1-second polling, sync at 5 seconds and settings without polling. Keep download progress, ETA, speed, errors and retry countdown visible.

- [ ] **Step 4: Restyle task and asset details**

Use green progress, open list grouping, semantic status text and restrained semantic color chips. No gradients and no dark nested card grid.

- [ ] **Step 5: Restyle item/search/collection drawers**

Use the same white drawer, gray divider and tactile close controls while preserving dialog names, search clear behavior and collection selection.

- [ ] **Step 6: Verify GREEN**

Run: `cd web && npm test -- --run src/features/status/ArchiveStatusPanel.test.tsx src/features/feed/FeedPage.test.tsx`

Expected: polling, tabs, download expansion, search and collection interactions pass.

- [ ] **Step 7: Commit checkpoint**

```bash
git add web/src/features/status web/src/features/feed web/src/components
git commit -m "feat: restyle archive utility panels"
```

### Task 5: 登录、初始设置和全局状态

**Files:**
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/features/setup/SetupPage.tsx`
- Modify: `web/src/features/auth/LocalLoginPage.tsx`
- Modify: `web/src/features/auth/DouyinLoginPage.tsx`
- Modify: related auth/setup tests

**Interfaces:**
- Consumes: `FriendlyButton`, `FriendlyIconButton`
- Preserves: setup/session API calls, remote browser canvas, WebSocket pointer/key transport and fullscreen live view

- [ ] **Step 1: Add failing shell tests**

```tsx
expect(screen.getByTestId("local-login-shell")).toHaveClass("friendly-auth-shell");
expect(screen.getByLabelText("本地管理员密码")).toBeVisible();
```

For Douyin login, add only a class expectation to the pre-login shell; existing tests remain the contract for canvas size, fullscreen live view, pointer events and OTP keys.

- [ ] **Step 2: Verify RED**

Run: `cd web && npm test -- --run src/features/auth src/features/setup`

Expected: FAIL on missing friendly shell classes; remote-browser behavior tests remain meaningful.

- [ ] **Step 3: Implement the light auth/setup system**

Use labels above fields, inline errors below inputs, friendly primary buttons and responsive single/two-column layouts. Restyle App loading/error states. Do not modify transport code or expose any session material.

- [ ] **Step 4: Verify GREEN**

Run: `cd web && npm test -- --run src/features/auth src/features/setup`

Expected: all authentication and setup tests pass, including pointer and keyboard forwarding.

- [ ] **Step 5: Commit checkpoint**

```bash
git add web/src/app web/src/features/auth web/src/features/setup
git commit -m "feat: unify archive onboarding surfaces"
```

### Task 6: 全量自动化与渲染验收

**Files:**
- Modify only when a failing verification reveals a concrete issue
- Temporary QA scripts/screenshots: outside repository

- [ ] **Step 1: Run the complete automated suite**

Run:

```bash
cd web
npm test -- --run
npm run lint
npm run build
```

Expected: all tests, ESLint and Vite production build exit 0.

- [ ] **Step 2: Start an isolated local QA app**

Use a temporary archive root and synthetic non-sensitive feed/download data. Do not point destructive fixtures at the production archive. Serve the exact production build on a temporary localhost port.

- [ ] **Step 3: Run Playwright responsive checks**

Because Browser bootstrap failed with `agent is not defined`, use the existing Playwright CLI fallback. Check 1440x1000, 1280x800, 1024x768, 430x932, 393x852 and 932x430. Record `innerWidth`, `scrollWidth`, panel bounding boxes, console errors and screenshots.

- [ ] **Step 4: Exercise core interactions**

Test collection switching, video play/pause, mobile collection/search/activity destinations, download task expansion and panel close. Confirm DOM/state changes after every action.

- [ ] **Step 5: Compare concepts and implementation**

Use `view_image` on both concept images and the latest desktop/mobile screenshots. Write a mismatch ledger for layout, type, color, borders/shadows, icons, media treatment and responsive behavior; fix every material mismatch and repeat tests/screenshots.

- [ ] **Step 6: Commit the verified implementation**

```bash
git add web docs/design docs/superpowers
git commit -m "feat: deliver friendly archive interface"
```

### Task 7: NAS 安全部署和产品复验

**Files:**
- Deploy source: `/vol3/1000/docker/douyin-nas-archive`
- Preserve archive: `/vol3/1000/抖音留影`

- [ ] **Step 1: Confirm clean checkpoint and deployment exclusions**

Run `git status --short`, `git log -1 --oneline`, `git remote -v`. Confirm no secrets, database, profile, cache or build artifact is staged.

- [ ] **Step 2: Sync safe source only**

Use rsync with the approved `all_server_key` and explicit exclusions for `.git`, `.env`, `.venv`, `node_modules`, `dist`, SQLite/DB files, caches, Playwright artifacts, archive data and browser profile.

- [ ] **Step 3: Rebuild only the archive service**

Run `docker compose build archive` and `docker compose up -d --no-deps archive` on the NAS source directory.

- [ ] **Step 4: Verify production**

Confirm container `running/healthy`, `/health/ready` archive/profile checks, `/api/status` preserves Douyin authentication, index references the new CSS/JS hashes, authenticated `/api/jobs` returns real data, and recent logs contain no `Traceback`, `ERROR` or `Exception`.

- [ ] **Step 5: Create a rollback tag**

Create an annotated local tag `checkpoint/friendly-ui-20260819` at the final verified commit. Do not push because no approved private GitLab remote is configured.
