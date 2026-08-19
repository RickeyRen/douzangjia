# “留影”电影资料库式暗亮主题实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将已修复布局的“留影”改为暗色默认、可持久切换亮色的电影资料库式界面。

**Architecture:** 通过 `ThemeProvider` 和 `<html data-theme>` 驱动一套语义 token，保留 checkpoint `fe6559a` 的桌面流式网格，再按媒体、工具面板、登录引导分阶段替换硬编码色彩。

**Tech Stack:** React, TypeScript, Vite, Tailwind CSS v4, Phosphor Icons, Vitest, Testing Library, Playwright CLI

**Spec:** `docs/superpowers/specs/2026-08-19-cinematic-theme-redesign-design.md`

## Global Constraints

- 默认主题必须是 `dark`，手动选择持久在 `liuying.theme.v1`。
- 不增加 npm 依赖、假数据或概念图中虚构的操作。
- 桌面三栏必须继续位于 CSS Grid 正常流。
- 主题切换不得重置收藏夹、搜索、媒体播放或面板状态。
- 不更改后端、认证、下载和远程浏览器协议。

### Task 1: 可持久主题基础

**Files:**
- Create: `web/src/theme/ThemeProvider.tsx`
- Create: `web/src/theme/ThemeToggle.tsx`
- Create: `web/src/theme/ThemeProvider.test.tsx`
- Modify: `web/src/main.tsx`
- Modify: `web/index.html`
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`

- [x] Write tests that expect default `data-theme="dark"`, toggle to light, `liuying.theme.v1=light`, remount recovery, and an accessible toggle label.
- [x] Run `npm test -- --run src/theme/ThemeProvider.test.tsx` and confirm RED because the theme modules do not exist.
- [x] Implement `ThemeProvider`, `useTheme`, `ThemeToggle`, and a pre-render inline initializer in `index.html`.
- [x] Add matching Chinese/English labels for switching to light/dark theme.
- [x] Run the targeted test and ESLint; commit `feat: add persistent archive themes`.

### Task 2: 暗色优先 token 与桌面外壳

**Files:**
- Modify: `web/src/styles/tokens.css`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/components/FriendlyButton.tsx`
- Modify: `web/src/components/FriendlyIconButton.tsx`
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/features/navigation/CollectionRail.tsx`
- Modify: `web/src/features/feed/DesktopItemDetails.tsx`
- Test: existing component and feed tests

- [x] Extend the desktop test to require a theme toggle in the toolbar while retaining flow-grid landmarks.
- [x] Confirm RED on the missing toggle.
- [x] Replace candy/physical CSS variables with spec `--app-*` variables and subtle 1px control borders.
- [x] Add `ThemeToggle` to the normal-flow top toolbar and make rail/details use open dividers rather than raised toy cards.
- [x] Run component/feed tests and ESLint; commit `feat: apply cinematic desktop theme`.

### Task 3: 媒体舞台和移动端

**Files:**
- Modify: `web/src/features/feed/FeedCard.tsx`
- Modify: `web/src/features/feed/GalleryViewer.tsx`
- Modify: `web/src/features/navigation/MobileNavigation.tsx`
- Modify: `web/src/styles/app.css`
- Test: `FeedCard.test.tsx`, `FeedPage.test.tsx`

- [x] Keep the existing RED assertions for `archive-media-stage`, `archive-media-frame`, and `friendly-mobile-nav`.
- [x] Implement desktop contained media, mobile snap-height geometry, semantic overlays and theme-aware bottom navigation.
- [x] Preserve and run video play/pause, mute, gallery and mobile reachability tests; commit `feat: theme cinematic media browsing`.

### Task 4: 工具面板和下载详情

**Files:**
- Modify: `ArchiveStatusPanel.tsx`, `DownloadMonitor.tsx`, `ItemDetailsSheet.tsx`, `MobileSearchSheet.tsx`, collection drawer markup
- Test: status and feed tests

- [x] Add a RED class contract for the theme-aware utility drawer while keeping real byte/speed/ETA assertions.
- [x] Convert overlays, tabs, status rows, progress bars, sync/settings and search/detail drawers to semantic theme tokens.
- [x] Remove gradients and glass blur; preserve polling and all interactions.
- [x] Run targeted tests and commit `feat: theme archive utility surfaces`.

### Task 5: 登录、初始设置和全局状态

**Files:**
- Modify: `App.tsx`, `SetupPage.tsx`, `LocalLoginPage.tsx`, `DouyinLoginPage.tsx`
- Test: existing auth/setup suites plus shell class contracts

- [x] Add RED theme-shell expectations without changing remote-browser behavior assertions.
- [x] Apply semantic surfaces, labeled fields, inline errors and theme toggle placement where authentication permits.
- [x] Re-run canvas, pointer, key and setup/session tests; commit `feat: theme archive onboarding`.

### Task 6: 全量验证、视觉对比和 NAS 部署

- [x] Run full Vitest, ESLint and Vite build.
- [x] Serve an isolated local QA archive and use Playwright fallback because Browser bootstrap returned `agent is not defined`.
- [x] Capture both themes at 1440x1000 plus dark mobile 430x932, and verify 1280x800, 1024x768, 393x852, 932x430 without overflow.
- [x] Exercise theme persistence, collection switch, video play/pause, mobile navigation, download expansion and panel close.
- [x] Use `view_image` on both concept images and final dark/light/mobile screenshots; fix all material mismatch-ledger findings.
- [x] Run fresh full verification, create checkpoint commit and annotated `checkpoint/cinematic-theme-ui-20260819` tag.
- [ ] Sync source with protected exclusions, rebuild only NAS archive service, then verify health, login preservation, asset hashes, real jobs API and clean recent logs.
