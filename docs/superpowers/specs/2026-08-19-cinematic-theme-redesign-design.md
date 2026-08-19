# “留影”电影资料库式暗亮主题设计

## 目标

把“留影”改为暗色优先的沉浸式媒体资料库，同时提供完整亮色主题。界面应该像成熟桌面媒体工具：视频是唯一视觉中心，导航和详情保持安静，信息层级依靠排版、留白和细分隔线，不依靠糖果色、玩具按钮或巨大圆角。

## 根因与保留项

- 原布局使用 `100dvh + overflow-hidden` 外加绝对定位右栏，在电脑端压缩/覆盖中央媒体。
- checkpoint `fe6559a` 已将左轨、中央媒体和右栏改为流式 CSS Grid。这一结构修复继续保留。
- checkpoint `4bb1572` 提供的可复用按钮组件保留 API，但视觉改为克制细边框，移除 4px 实体底边。

## 视觉基准

- 默认暗色：`docs/design/liuying-cinematic-dark-concept.png`
- 对等亮色：`docs/design/liuying-cinematic-light-concept.png`

概念图只决定布局、色彩、排版、边界、图标和信息层级。图中虚构的文件名、分辨率、大小、播放时长或同步结果不得添加；产品只渲染真实 API 数据。

## 主题模型

- 主题值为 `dark | light`，默认 `dark`。
- 用户点击顶栏主题按钮在两者之间切换。
- 选择写入 `localStorage` 的版本化键 `liuying.theme.v1`，刷新和重启浏览器后保留。
- 主题通过 `<html data-theme="dark|light">` 驱动语义 CSS 变量，组件不应在渲染分支中复制两套标记。
- 初始加载在 React 渲染前应用持久值，避免亮色闪烁。
- 主题按钮必须有当前状态、下一操作的可访问文字，不只依赖太阳/月亮图标。

## 色彩 token

### 暗色（默认）

- `--app-bg: #0B0D10`
- `--app-surface: #12161B`
- `--app-surface-raised: #171B21`
- `--app-stage: #0E1216`
- `--app-text: #F2F3F5`
- `--app-muted: #8D949E`
- `--app-faint: #626A74`
- `--app-line: #252A31`
- `--app-line-strong: #343A43`
- `--app-accent: #59B98A`
- `--app-accent-soft: rgba(89, 185, 138, .11)`
- `--app-warning: #D9A354`
- `--app-danger: #D76B6B`

### 亮色

- `--app-bg: #F4F5F6`
- `--app-surface: #FFFFFF`
- `--app-surface-raised: #FFFFFF`
- `--app-stage: #171B20`
- `--app-text: #272A2E`
- `--app-muted: #717780`
- `--app-faint: #9BA0A7`
- `--app-line: #DEE1E5`
- `--app-line-strong: #C9CDD2`
- `--app-accent: #4E9E78`
- `--app-accent-soft: rgba(78, 158, 120, .10)`
- `--app-warning: #B97D2E`
- `--app-danger: #C45656`

色彩绝不使用渐变、霓虹、紫色或外发光。翡翠绿是唯一产品强调色；黄/红只用于真实警告和失败。

## 几何、排版与动效

- 应用外壳和大区域使用 0–16px 圆角；对话抽屉 18px；仅图标按钮 10–12px。
- 默认不为导航轨和右栏添加浮起卡片阴影；使用 1px 分隔线和留白分组。
- 媒体舞台可以有一层克制的内阴影，但不在视频上叠加彩色洗色。
- 使用 Geist/SF Pro/PingFang SC 字体栈；导航 13–14px、工具 12–14px、正文 14–16px、主标题不超过 24px。
- 交互过渡 140–180ms，只动画 `transform` 和 `opacity`；不增加循环动画、磁吸、粒子或滚动监听器。

## 布局

- `>=1280px`: `248px minmax(520px, 1fr) 330px` 三栏流式网格。
- `960–1279px`: `224px minmax(0, 1fr)` 双栏，作品详情进入抽屉。
- `<960px`: 单栏媒体浏览，白/暗主题都保留顶部收藏夹与主题入口、底部五入口导航和安全区。
- 桌面顶栏、中央舞台、翻页工具必须在正常网格流中。
- 9:16 媒体必须 `object-contain`，在 1440x1000、1280x800、1024x768 无裁切、无遮挡、无水平溢出。

## 功能面

- 收藏导航：开放轨道 + 细分隔，选中行只用左侧绿线和浅绿底。
- 媒体：保留播放/暂停、静音、图集滑动、视频进度、竖向切换和自动加载。
- 详情：开放列表 + 分隔线，只显示真实作者、描述、日期、收藏夹和本地原文件状态。
- 下载：保留队列/文件进度、字节、速度、ETA、状态、错误、重试次数和倒计时；去掉渐变。
- 登录/设置：使用同一主题 token；抖音远程浏览器的 WebSocket、canvas 坐标、键盘和手势协议不变。

## 测试与部署

- TDD 首先锁定：默认暗色、点击切换亮色、localStorage 持久、刷新恢复、可访问标签。
- 保留已有的桌面网格测试、媒体交互测试、下载轮询和详情测试、登录手势/键盘测试。
- 完整执行 Vitest、ESLint 和 Vite 生产构建。
- Browser/IAB 启动失败为 `agent is not defined`，最终使用已允许的 Playwright CLI 回退验收 1440x1000、1280x800、1024x768、430x932、393x852、932x430。
- 使用 `view_image` 对比概念和最终截图，至少检查布局、色彩、排版、边界、图标和响应式六项。
- NAS 部署仍排除 `.env`、SQLite、媒体、Chromium profile、cookie、缓存和构建产物，只重建 archive 服务。

## 不做

- 不添加删除、分享、点赞、评论、暂停队列或取消任务。
- 不添加第三方主题、动画、图标或字体依赖。
- 不更改抖音获取、下载、数据库或认证协议。
