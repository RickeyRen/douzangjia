# 留影 · 抖音收藏 NAS 归档

一个只运行在 NAS 上的私有归档服务：使用抖音扫码登录，按原收藏夹名称下载原文件，并提供沉浸式本地浏览页。

## 保留规则

- `objects/` 保存唯一原文件，已下载内容永不因远端取消收藏而删除。
- `library/<收藏夹名>/` 是方便人工浏览的硬链接视图；同一作品进入多个收藏夹时不重复占用空间。
- SQLite 使用 WAL，下载使用 `.part` 断点续传和原子改名。
- 扫码会话和 Cookie 仅保存在 NAS；数据库中的 Cookie 使用 Fernet 加密，完整 Chromium Profile 使用 `0700` 权限保存。

## 运行

```bash
cp .env.example .env
# 填入新生成的 ARCHIVE_MASTER_KEY，并根据 NAS 设置 ARCHIVE_PATH/PUID/PGID
docker compose up -d --build
```

默认访问 `http://NAS-IP:8099` 。首次打开时先创建 NAS 本地管理密码，再扫描页面中的抖音二维码。扫码成功会立即启动首次全量归档，之后每 5 分钟增量同步。

登录页使用 Chromium CDP + WebSocket 传送最新 JPEG 帧，旧帧不会排队；浏览器不支持 CDP 时会自动退回 MJPEG 兼容模式。画面固定为 1280×800，并在网页窗口内完整等比显示。

## 持久登录与安全边界

- 容器内 Profile 固定为 `/archive/data/chromium-profile`，宿主机对应 `${ARCHIVE_PATH}/data/chromium-profile`。
- 服务每次启动都会把目录权限修正为 `0700`。这可以隔离普通同机用户，但 NAS 管理员、`root` 和有 Docker 管理权限的人仍能读取完整浏览器资料。
- Profile、数据库中的加密 Cookie 和收藏同步共用同一浏览器设备环境；正常重启不会主动清除会话，因此通常不需要重新扫码，也更少触发滑动验证。
- 抖音仍可能因自身风控、Cookie 到期、IP 或设备环境变化要求重新验证，本项目不会绕过或自动破解验证码。
- 删除 `chromium-profile` 会让抖音把下一次登录视为新浏览器，并强制重新扫码。不要把 Profile 放入 Git、Docker 构建上下文或日志。

如果 Chromium 报告 Profile 被占用，不要结束来源不明的浏览器进程；先确认只有本项目的容器使用该归档目录，再正常停止该服务后检查。

## Profile 恢复

检测到损坏时，服务会把旧目录保留为同级的 `chromium-profile.<原因>.<时间>`，不会自动删除。只有容器停止后才能恢复：

```bash
docker compose stop archive
mv "${ARCHIVE_PATH}/data/chromium-profile" "${ARCHIVE_PATH}/data/chromium-profile.current-backup"
mv "${ARCHIVE_PATH}/data/chromium-profile.<原因>.<时间>" "${ARCHIVE_PATH}/data/chromium-profile"
chmod 700 "${ARCHIVE_PATH}/data/chromium-profile"
docker compose up -d archive
```

恢复前请把占位路径替换成实际目录，并保留 `current-backup`，确认会话可用后再自行决定是否清理。

## English

NAS-only permanent archive for Douyin favorite collections. It keeps canonical media in `objects/`, projects collection folders under `library/`, retains a private Chromium profile across restarts, encrypts its cookie backup, and serves a responsive local web viewer with a latest-frame WebSocket transport.
