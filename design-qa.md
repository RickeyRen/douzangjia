# 抖藏家 Credit Pros 视觉复刻 QA

## 目标与范围

- 唯一视觉参考：`https://rondesignlab.com/cases/credit-pros-saas-dashboard-ui-ux-design`
- 实现目标：保留参考案例的极黑画布、轻字重、深灰圆角卡片、彩色状态光点、非对称数据层级；所有品牌、文案、图片和指标替换为抖藏家的真实内容。
- 核心页面：首页、全部归档、多作品视图、博主主页、作品详情、活动/下载/同步抽屉、设置、本地账户与抖音登录。
- 验证尺寸：桌面 1440×1000、参考同尺寸 1050×870、iPhone 15 Pro Max 430×932。

## 参考证据

- 完整案例页面已从顶部滚动到底部，共留存 65 个静默视口截图：`/tmp/douzangjia-credit-pros-source/desktop-00.png` 至 `desktop-64.png`。
- 重点参考区：`desktop-30.png`（实时卡片与移动仪表盘）、`desktop-35.png`（桌面仪表盘构图）、`desktop-45.png`（黑色、绿、黄、红、紫、蓝、青配色体系）。
- 参考与实现同为 1050×870 的并排对照：`/tmp/douzangjia-credit-pros-comparison-1050x870.png`。

## 实现证据

- 桌面首页：`/tmp/douzangjia-credit-pros-implementation-desktop-final.png`，1440×1000。
- 同尺寸首页：`/tmp/douzangjia-credit-pros-implementation-1050x870.png`，1050×870。
- iPhone 首页：`/tmp/douzangjia-credit-pros-implementation-iphone15pm.png`，430×932。
- iPhone 博主主页：`/tmp/douzangjia-credit-pros-implementation-creator-iphone15pm-final.png`，430×932。
- 生产地址：`http://192.168.0.6:8099/`。

## 视觉检查

- Typography：标题使用较大字号与轻字重，数值使用等宽字体；桌面和移动端均无重要文本裁切。
- Spacing：桌面采用 12 列非对称 Bento 阅读顺序；移动端改为单列首页与双列作品，不依赖水平滚动。
- Color：近黑背景、白/灰信息层级，黄为主要动作，蓝/紫/绿/青/红用于不同状态；颜色之外仍有文字和图标语义。
- Radius / borders：主要卡片 20–26px 圆角、细边框和轻内高光，与参考的悬浮深色面板一致。
- Image quality：作品封面使用真实归档媒体并保持 `object-fit: cover`；未复制或热链参考案例的品牌图片。
- Copy：全部为真实抖藏家数据；首页显示抖音昵称、抖音号、连接状态、实时任务、速度、存储、内存、CPU、吞吐、队列和来源进度。

## 功能与响应式检查

- 80 个前端测试通过；TypeScript/Vite 生产构建通过；ESLint 通过。
- NAS 容器重建后为 `healthy`，`/health/ready` 返回 `archiveRoot: ok`、`browserProfile: ok`。
- 桌面 1440×1000：四区应用壳正确显示，正文无水平溢出，首页当前同步活动和真实指标每秒更新。
- iPhone 430×932：首页 `scrollWidth === clientWidth === 430`；底部五项导航可见，核心指标无需悬停。
- 移动收藏夹抽屉可打开并显示 17 个可交互类目条目与真实圆环进度。
- 多作品视图加载 20 个首屏条目；卡片直接显示真实抖音号，缺失身份时才显示“暂未获取”。
- 博主主页可从作品作者进入，显示抖音号、远程作品/粉丝/本地作品、全部保存与追更操作，并列出本地已收藏作品。
- iPhone 博主作品网格最终为两列（`201px 201px`），页面与网格均无水平溢出。
- 浏览器控制台错误和警告：0。

## 迭代记录

1. 初版完成视觉 token、双层导航壳与首页 Bento。
2. 实机桌面检查发现实时活动大标题继承了单行省略规则；改为可换行轻标题并复验完整显示。
3. 实机 iPhone 检查发现博主页三列作品卡过窄；定位为高优先级选择器覆盖移动规则，修正为双列并复验无溢出。
4. 完成桌面、同尺寸对照、iPhone 首页、iPhone 博主页、抽屉、网格、作者跳转与控制台检查。

final result: passed
