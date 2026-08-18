# 持久抖音浏览器与低延迟远程控制设计

## 背景

当前登录浏览器使用临时 Chromium 档案并运行在容器 `/tmp` 中。容器重启后，Cookie 之外的 LocalStorage、IndexedDB、Service Worker 和设备信任信息全部丢失，抖音容易把下一次登录判断为新设备，导致重复扫码和图形验证码。

当前远程画面由 Playwright 周期性截图，再以 12 FPS MJPEG 传给网页。鼠标事件通过多个 HTTP 请求串行提交，状态另行轮询。这会产生截图开销、旧帧排队和输入往返延迟，操作体验明显卡顿。

## 目标

- 登录、收藏同步和重新验证复用同一份 NAS Chromium 设备档案。
- 容器普通重启后优先恢复既有抖音登录，不重复扫码。
- 只有抖音明确判定登录无效时，才要求用户重新登录。
- 将远程浏览器切换为只保留最新帧的低延迟传输，避免播放积压画面。
- 点击、拖动和受限键盘输入在一个长连接中即时转发。
- 保留当前加密 Cookie 数据和 MJPEG 兼容回退。

## 非目标与外部边界

- 无法修改抖音服务端设置的短信验证码有效期、图形验证码策略或 Cookie 服务端过期时间。
- 不承诺完全消除抖音风控；目标是避免应用自身反复制造“新设备”。
- 不向公网暴露远程浏览器，也不增加远程桌面或任意键盘快捷键能力。
- 本次不引入 WebRTC、STUN/TURN、noVNC 或音频传输。

## 方案选择

采用“持久 Chromium 档案 + CDP Screencast + WebSocket 输入/状态”的组合方案。

不继续以提高 MJPEG 帧率作为主方案，因为 Playwright 截图和 HTTP 输入队列仍会保留主要延迟来源。不采用 WebRTC/noVNC，因为局域网单用户场景不需要额外的媒体协商、转码和远程桌面依赖。

## 架构

### BrowserProfileStore

- 档案目录固定为 `/archive/data/chromium-profile`，由配置项派生，不接受任意外部路径。
- 启动前创建目录并设置 `0700`；发现所有者或权限异常时拒绝启动浏览器，并给出可操作错误。
- Chromium 以 `launch_persistent_context` 打开该目录，登录和同步均复用此上下文。
- 浏览器仍以容器用户 `PUID:PGID` 运行，容器保持只读根文件系统、丢弃 capabilities 和 `no-new-privileges`。
- 完整档案可能包含明文浏览器状态；用户已接受该取舍。现有 `auth_sessions.encrypted_cookies` 继续作为加密恢复与健康判断来源。

### BrowserCoordinator

- 由单一协调器拥有 Playwright、persistent context、页面和 CDP 会话。
- 登录交互与收藏同步共享同一上下文，但通过异步锁串行使用页面，避免两个任务同时修改浏览器状态。
- 登录成功后不删除档案；关闭登录页面时保留上下文或在安全点正常关闭，使 Chromium 完成档案刷盘。
- 应用启动后先检查持久上下文中的抖音 Cookie 和登录页状态。已登录则更新加密 Cookie 记录并直接触发增量同步；失效才进入扫码流程。
- 容器停止时优先正常关闭页面和上下文。异常断电后依靠 Chromium 自身的 profile 恢复；若档案损坏，隔离损坏目录并回退到加密 Cookie 或重新登录，不自动删除原目录。

### 低延迟画面

- 对交互页面创建 CDP Session，调用 `Page.startScreencast`，格式 JPEG，默认质量 68，最大尺寸 1280×800。
- 收到 `Page.screencastFrame` 后立即确认 frame session id。
- 每个观看连接最多保留一帧待发送数据；新帧到达时覆盖未发送旧帧，不形成历史队列。
- 默认目标为 20 FPS。服务端根据发送耗时和丢帧比例在 12–24 FPS 等效范围内自适应，不通过缓存补帧。
- WebSocket 二进制消息承载 JPEG；小型 JSON 消息承载状态、尺寸和错误。
- 浏览器不支持 CDP Screencast 或 WebSocket 建连失败时，网页自动回退现有 MJPEG。

### 低延迟输入

- 同一 WebSocket 接收 `pointer`、`key` 和 `viewport` 消息。
- 点击和抬起立即处理；鼠标移动在客户端以动画帧合并，服务端只保留尚未执行的最新移动。
- 拖动维持现有 12 像素阈值和分步移动，但不再经过多次 HTTP 往返。
- 键盘仅允许数字、退格、回车和 Tab；不接受组合快捷键、剪贴板、脚本或任意文本。
- 所有坐标归一化到 Chromium 视口，尺寸变化由 `viewport` 状态显式同步。

### 认证与安全

- WebSocket 握手必须具有有效 `archive_session`，并验证 `Origin` 与当前 NAS 主机一致。
- 登录会话 id 使用现有随机不可预测 id；不存在或已结束的会话立即关闭连接。
- WebSocket 不记录 Cookie、验证码、键值内容或完整 URL 查询参数。
- 浏览器档案不加入 Git、镜像或备份源码包；`.dockerignore` 和 `.gitignore` 增加明确保护。
- 健康检查只报告 coordinator/profile/screencast 是否可用，不泄露账号状态细节。

## 数据流

1. 应用启动，BrowserProfileStore 校验并准备私有档案目录。
2. BrowserCoordinator 打开 persistent context，检测既有抖音登录。
3. 若已登录，刷新加密 Cookie 记录并触发同步；网页不展示扫码入口。
4. 若未登录，用户启动登录，协调器在同一 context 中打开抖音页面。
5. 网页建立 WebSocket；服务端推送视口元数据和最新 JPEG 帧。
6. 用户输入经 WebSocket 进入协调器，由 Playwright/CDP 在当前页面执行。
7. 登录成功后更新加密 Cookie，关闭交互页/视频流并开始首次全量同步。

## 状态与错误处理

- `restoring`：正在检查持久档案，不提前显示扫码按钮。
- `authenticated`：持久登录有效。
- `awaiting_scan`：确实需要用户登录。
- `profile_locked`：同一档案被另一 Chromium 占用；不强杀未知进程，报告明确错误。
- `profile_corrupt`：保留并重命名损坏档案，尝试用加密 Cookie 建立新档案。
- `stream_fallback`：CDP/WebSocket 不可用，切回 MJPEG，并在 UI 显示降级状态。
- 网络断开时网页指数退避重连；重连后只显示最新帧。

## 性能预算

- 局域网正常情况下，指针到服务端接收的目标延迟小于 50 ms。
- 不积帧；客户端显示帧相对服务端最新帧最多落后一帧。
- 1280×800 默认 20 FPS，单连接内存中的帧缓冲不超过两张 JPEG。
- 状态不再以 250 ms 轮询；登录状态变化由 WebSocket 推送，保留低频 5 秒兜底检查。

## 测试与验收

### 自动化测试

- profile 目录创建、权限修复、锁冲突和损坏回退。
- persistent context 在模拟重启后保留 Cookie 与 LocalStorage。
- 启动恢复已登录状态时不创建新扫码会话。
- WebSocket 鉴权、Origin 校验、未知会话关闭和消息白名单。
- screencast ack、最新帧覆盖、慢客户端不积帧和 MJPEG 回退。
- 指针拖动、点击、数字键、退格与回车顺序。
- React 页面重连、Canvas 最新帧绘制、输入合并和降级提示。

### NAS 真实验收

- 构建、部署、容器健康分别报告。
- 完成一次真实抖音登录并确认加密 Cookie 已更新。
- 重启容器后无需扫码，直接恢复抖音已登录状态并完成一次真实增量同步。
- 在 1280×800 页面连续点击、拖动和输入，确认无旧帧回放；记录实际帧率和交互延迟。
- 人为断开 WebSocket，确认自动重连或 MJPEG 回退。

## 迁移与回滚

- 首次启动自动创建持久档案；若数据库已有加密 Cookie，则注入同一 persistent context 后再验证登录。
- 旧 MJPEG、HTTP pointer/key 路由暂时保留一个版本，便于前端回退和快速回滚。
- 回滚只需切回旧镜像；持久档案目录保留，不自动删除。
- 每个验证通过的阶段创建本地 checkpoint commit；仓库若无批准的私有 GitLab 远程，只保留本地 checkpoint 并如实报告。
