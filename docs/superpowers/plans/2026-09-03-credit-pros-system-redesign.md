# 抖藏家 Credit Pros 全站视觉重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将抖藏家所有现有页面统一重构为 Credit Pros 风格，并保持真实数据、下载逻辑、登录会话和响应式能力不变。

**Architecture:** 保留 React 状态、API 和 SSE 数据层，新增轻量应用外壳与专用仪表盘视觉组件，通过 CSS 变量统一全站主题。首页采用真实数据驱动的 Bento 栅格，媒体库按单作品/网格两种模式复用现有业务组件，移动端通过同一 DOM 结构和断点适配。

**Tech Stack:** React 19、TypeScript、Vite、Vitest、Testing Library、Phosphor Icons、原生 CSS/SVG、FastAPI、Docker Compose

**Spec:** `docs/superpowers/specs/2026-09-03-credit-pros-system-redesign-design.md`

## Global Constraints

- 不复制 Credit Pros 的品牌、文案、图标、图片、插画或业务数据。
- 不修改后端数据模型，不添加远程字体或新的图表运行时依赖。
- 暗色为默认；亮色继续可切换。
- 中文正文不得小于 13px；交互目标至少 44×44px。
- iPhone 15 Pro Max 使用 430×932 CSS 像素验收。
- 所有图表、进度和指标必须来自现有 API/SSE 数据。
- 保留 NAS 上的 `.env`、数据库、归档目录和 Chromium 登录配置。

---

### Task 1: Credit Pros 视觉变量与基础组件

**Files:**
- Modify: `web/src/styles/tokens.css`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/components/FriendlyButton.tsx`
- Modify: `web/src/components/FriendlyIconButton.tsx`
- Modify: `web/src/components/ProgressRing.tsx`
- Create: `web/src/styles/creditProsSystem.test.ts`

**Interfaces:**
- Consumes: 现有 `data-theme`、`data-icon-tone` 和按钮属性。
- Produces: `--app-*` 主题变量、`.app-card`、`.app-status-dot`、`.app-icon-button`、统一按钮和进度圆环样式。

- [ ] **Step 1: 编写视觉变量失败测试**

```ts
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("Credit Pros visual system", () => {
  const tokens = readFileSync(new URL("./tokens.css", import.meta.url), "utf8");
  const app = readFileSync(new URL("./app.css", import.meta.url), "utf8");
  it("defines the dark canvas and semantic accents", () => {
    expect(tokens).toContain("--app-bg: #050505");
    expect(tokens).toContain("--app-warning: #ffd84d");
    expect(tokens).toContain("--app-violet: #9a5cff");
  });
  it("provides the shared elevated card primitive", () => {
    expect(app).toContain(".app-card");
    expect(app).toContain("prefers-reduced-motion");
  });
});
```

- [ ] **Step 2: 验证测试先失败**

Run: `cd web && npm test -- src/styles/creditProsSystem.test.ts`
Expected: FAIL，缺少新的视觉变量与 `.app-card`。

- [ ] **Step 3: 实现颜色、排版、卡片、按钮、状态点和动效变量**

将暗色变量按 spec 精确写入 `tokens.css`，为亮色设置独立中性色。把现有 `friendly-*` 组件映射到统一基础类，并在 `app.css` 加入：

```css
.app-card {
  border: 1px solid var(--app-line);
  border-radius: var(--app-card-radius);
  background: linear-gradient(145deg, rgb(255 255 255 / 2.5%), transparent 42%), var(--app-surface);
  box-shadow: inset 0 1px rgb(255 255 255 / 3%), 0 24px 70px rgb(0 0 0 / 28%);
}
```

- [ ] **Step 4: 运行基础组件与主题测试**

Run: `cd web && npm test -- src/styles/creditProsSystem.test.ts src/theme/ThemeProvider.test.tsx src/components/FriendlyButton.test.tsx`
Expected: PASS。

- [ ] **Step 5: 创建 checkpoint**

```bash
git add web/src/styles web/src/components
git commit -m "feat: establish credit pros visual system"
```

### Task 2: 统一桌面与移动应用外壳

**Files:**
- Create: `web/src/features/navigation/PrimaryRail.tsx`
- Create: `web/src/features/navigation/AppShell.tsx`
- Create: `web/src/features/navigation/AppShell.test.tsx`
- Modify: `web/src/features/navigation/CollectionRail.tsx`
- Modify: `web/src/features/navigation/MobileNavigation.tsx`
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/styles/app.css`
- Modify: `web/src/i18n/zh-CN.ts`
- Modify: `web/src/i18n/en.ts`

**Interfaces:**
- Consumes: `UtilityPanel`, `LibrarySource[]`, `DashboardSnapshot | null` 与 `MobileDestination`。
- Produces: `AppShell({children, context, details})`、`PrimaryRail({active,onOpen})`，以及全站共享的三列桌面结构。

- [ ] **Step 1: 编写外壳结构失败测试**

```tsx
render(<AppShell primary={<span>primary</span>} context={<span>context</span>} details={<span>details</span>}><main>content</main></AppShell>);
expect(screen.getByTestId("app-primary-rail")).toBeInTheDocument();
expect(screen.getByTestId("app-context-rail")).toBeInTheDocument();
expect(screen.getByTestId("app-main-stage")).toHaveTextContent("content");
expect(screen.getByTestId("app-details-rail")).toBeInTheDocument();
```

- [ ] **Step 2: 验证测试先失败**

Run: `cd web && npm test -- src/features/navigation/AppShell.test.tsx`
Expected: FAIL，`AppShell` 尚不存在。

- [ ] **Step 3: 实现外壳与导航**

`AppShell` 只负责区域组合；`PrimaryRail` 负责首页、收藏、搜索、活动、设置和账号头像；`CollectionRail` 只负责来源与圆环进度。`FeedPage` 保持业务状态不变，将当前页面内容注入 `AppShell`。

- [ ] **Step 4: 补齐中英文并运行导航回归**

Run: `cd web && npm test -- src/features/navigation/AppShell.test.tsx src/features/feed/FeedPage.test.tsx src/i18n/i18n.test.ts`
Expected: PASS。

- [ ] **Step 5: 创建 checkpoint**

```bash
git add web/src/features/navigation web/src/features/feed/FeedPage.tsx web/src/styles/app.css web/src/i18n
git commit -m "feat: unify archive application shell"
```

### Task 3: 重构真实数据首页

**Files:**
- Create: `web/src/features/home/DashboardHero.tsx`
- Create: `web/src/features/home/StorageCard.tsx`
- Create: `web/src/features/home/QueueCard.tsx`
- Modify: `web/src/features/home/DashboardPrimitives.tsx`
- Modify: `web/src/features/home/LiveActivitySection.tsx`
- Modify: `web/src/features/home/HomePage.tsx`
- Modify: `web/src/features/home/HomePage.test.tsx`
- Modify: `web/src/styles/app.css`

**Interfaces:**
- Consumes: `DashboardSnapshot` 和 `MetricPoint[]`。
- Produces: `DashboardHero`、`StorageCard`、`QueueCard`、`DashboardMetric` 和 `DashboardTrend`，均为纯展示组件。

- [ ] **Step 1: 为首屏层级和真实数据编写失败测试**

```tsx
expect(screen.getByTestId("dashboard-hero")).toHaveTextContent("正在");
expect(screen.getByTestId("dashboard-primary-metrics")).toHaveTextContent("125 MB/s");
expect(screen.getByTestId("dashboard-storage-card")).toHaveAttribute("data-used-percent", "42");
expect(screen.getByTestId("dashboard-queue-card")).toHaveTextContent("等待");
```

- [ ] **Step 2: 验证测试先失败**

Run: `cd web && npm test -- src/features/home/HomePage.test.tsx`
Expected: FAIL，新的 hero、storage 和 queue 结构不存在。

- [ ] **Step 3: 实现 12 列 Bento 首页**

把当前顺序区块改为 `dashboard-bento`；首屏放置实时活动、四项核心指标和两张趋势图。其余账户、来源、服务信息在后续网格中。SVG 趋势图增加渐变面积、网格线和当前值，但数据仍来自 `series`。

- [ ] **Step 4: 验证实时断连、空历史和账号缺失状态**

新增用例确认 `connected=false`、`series=[]`、`account=null` 均保持完整布局与可读文案。

- [ ] **Step 5: 运行首页与流测试**

Run: `cd web && npm test -- src/features/home`
Expected: PASS。

- [ ] **Step 6: 创建 checkpoint**

```bash
git add web/src/features/home web/src/styles/app.css
git commit -m "feat: redesign live archive dashboard"
```

### Task 4: 重构媒体库、博主页与视频详情

**Files:**
- Create: `web/src/features/feed/MediaToolbar.tsx`
- Modify: `web/src/features/feed/FeedPage.tsx`
- Modify: `web/src/features/feed/FeedCard.tsx`
- Modify: `web/src/features/feed/FeedGrid.tsx`
- Modify: `web/src/features/feed/CreatorProfile.tsx`
- Modify: `web/src/features/feed/DesktopItemDetails.tsx`
- Modify: `web/src/features/feed/ItemDetailsSheet.tsx`
- Modify: `web/src/features/feed/FeedPage.test.tsx`
- Modify: `web/src/features/feed/FeedCard.test.tsx`
- Modify: `web/src/features/feed/ItemDetails.test.tsx`
- Modify: `web/src/styles/app.css`

**Interfaces:**
- Consumes: 当前 `FeedItem`、`Creator`、`FeedViewMode` 和回调。
- Produces: `MediaToolbar`；其余组件保持公开 props 兼容。

- [ ] **Step 1: 编写关键媒体体验失败测试**

```tsx
expect(screen.getByRole("button", { name: /网格/ })).toBeInTheDocument();
expect(screen.getByText(/抖音号/)).toBeInTheDocument();
expect(screen.getByRole("button", { name: /归档全部作品/ })).toBeInTheDocument();
expect(screen.getByTestId("desktop-details")).toHaveTextContent("文件大小");
```

- [ ] **Step 2: 验证测试先失败**

Run: `cd web && npm test -- src/features/feed/FeedPage.test.tsx src/features/feed/FeedCard.test.tsx src/features/feed/ItemDetails.test.tsx`
Expected: 至少一个新的工具栏或详情结构断言失败。

- [ ] **Step 3: 实现统一工具栏和沉浸单作品舞台**

将来源标题、搜索、当前分类归档、视图切换与主题按钮移入 `MediaToolbar`。单作品模式在桌面使用中央媒体舞台 + 详情栏；移动端保持全屏媒体和底部安全区。

- [ ] **Step 4: 实现 Credit Pros 风格网格与博主页**

网格桌面 `repeat(auto-fill, minmax(190px, 1fr))`，移动端两列。博主页使用大头像、身份、三项统计和两个动作组成 Bento 头部；现有自动分页逻辑保持不变。

- [ ] **Step 5: 完整显示远端身份与本地文件信息**

作者和抖音号在卡片遮罩、桌面详情和移动详情中可见；缺失身份沿用刷新状态。文件大小、分辨率、编码、本地路径和远端状态继续来自 `RichItemDetails`。

- [ ] **Step 6: 运行媒体回归测试**

Run: `cd web && npm test -- src/features/feed`
Expected: PASS。

- [ ] **Step 7: 创建 checkpoint**

```bash
git add web/src/features/feed web/src/styles/app.css
git commit -m "feat: redesign media and creator experience"
```

### Task 5: 统一抽屉、登录、设置与响应式状态

**Files:**
- Modify: `web/src/features/status/ArchiveStatusPanel.tsx`
- Modify: `web/src/features/status/DownloadMonitor.tsx`
- Modify: `web/src/features/auth/LocalLoginPage.tsx`
- Modify: `web/src/features/auth/DouyinLoginPage.tsx`
- Modify: `web/src/features/auth/OwnerMigrationPage.tsx`
- Modify: `web/src/features/setup/SetupPage.tsx`
- Modify: `web/src/app/App.tsx`
- Modify: `web/src/features/auth/LocalAccountPages.test.tsx`
- Modify: `web/src/features/auth/DouyinLoginPage.test.tsx`
- Modify: `web/src/styles/app.css`

**Interfaces:**
- Consumes: 现有登录、设置、下载、同步 API 与回调。
- Produces: 统一 `.auth-shell`、`.status-drawer`、`.app-state-card` 视觉结构，不改变请求协议。

- [ ] **Step 1: 编写登录和错误状态结构失败测试**

```tsx
expect(screen.getByRole("heading", { name: /抖藏家/ })).toBeInTheDocument();
expect(screen.getByRole("button")).toHaveClass("friendly-button");
expect(document.querySelector(".auth-shell")).toBeTruthy();
```

- [ ] **Step 2: 验证测试先失败**

Run: `cd web && npm test -- src/features/auth/LocalAccountPages.test.tsx src/features/auth/DouyinLoginPage.test.tsx`
Expected: FAIL，统一认证外壳尚未出现。

- [ ] **Step 3: 统一认证、抽屉、加载、错误和空状态**

保留所有表单字段与业务回调，只重组展示容器。`App.tsx` 的读取失败状态改为居中 `app-state-card`，保证标题、原因和重试按钮清晰。

- [ ] **Step 4: 编写并验证响应式 CSS**

断点按 spec 实现；为 430×932 设置安全区、双列媒体网格、底部导航和全宽抽屉；为 1280px 设置收拢上下文栏；为 1440px 启用完整三级布局。

- [ ] **Step 5: 运行认证、状态和全量前端测试**

Run: `cd web && npm test`
Expected: 全部 PASS。

- [ ] **Step 6: 创建 checkpoint**

```bash
git add web/src/features/auth web/src/features/setup web/src/features/status web/src/app/App.tsx web/src/styles/app.css
git commit -m "feat: unify responsive system surfaces"
```

### Task 6: 构建、浏览器验收与 NAS 部署

**Files:**
- Modify: `docs/designs/douzangjia-credit-pros-acceptance.md`
- Create: `docs/designs/douzangjia-credit-pros-desktop.png`
- Create: `docs/designs/douzangjia-credit-pros-mobile.png`

**Interfaces:**
- Consumes: 完成后的 Web 应用、现有 Docker Compose 服务与 NAS SSH 配置。
- Produces: 可回滚 checkpoint、验收截图、部署记录和健康的 `douzangjia` 容器。

- [ ] **Step 1: 运行静态检查与构建**

Run: `cd web && npm test && npm run build && npm run lint`
Expected: 全部成功，测试数不少于现有 76 个。

- [ ] **Step 2: 运行后端回归**

Run: `uv run pytest && uv run ruff check .`
Expected: 全部 PASS。

- [ ] **Step 3: 使用本地生产构建进行桌面和移动验收**

在 1440×900、1280×800、430×932 检查首页、单作品、网格、博主页、详情、下载、同步、设置和登录/错误状态；后台静默截图写入 `docs/designs/`。

- [ ] **Step 4: 检查 SSH 配置并只使用已验证别名连接 NAS**

Run: `sed -n '1,240p' ~/.ssh/config`
Expected: 找到指向 `192.168.0.6`、用户 `RENJIAWEI`、明确 `IdentityFile` 和 `IdentitiesOnly yes` 的别名；用 `ssh -o BatchMode=yes <alias> true` 复验。

- [ ] **Step 5: 部署且保留持久化数据**

同步源代码时排除 `.env`、数据库、归档目录、Chromium profile、缓存和构建产物；在 `/vol3/1000/docker/douyin-nas-archive` 重建 `archive` 服务。

- [ ] **Step 6: 验证生产应用**

确认容器健康、HTTP 入口可访问、SSE 更新、登录会话仍有效，并在桌面和 430×932 重新截图。

- [ ] **Step 7: 记录验收并创建最终 checkpoint**

```bash
git add docs/designs
git commit -m "docs: record credit pros redesign acceptance"
```

- [ ] **Step 8: 检查私有 GitLab 后再决定推送**

Run: `git remote -v`
Expected: 只有在远程明确属于用户批准的私有 GitLab 时推送当前分支和本次新增标签；没有远程则保留本地 checkpoint 并如实报告。
