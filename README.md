# 留影 · 抖音收藏 NAS 归档

一个只运行在 NAS 上的私有归档服务：使用抖音扫码登录，按原收藏夹名称下载原文件，并提供沉浸式本地浏览页。

## 保留规则

- `objects/` 保存唯一原文件，已下载内容永不因远端取消收藏而删除。
- `library/<收藏夹名>/` 是方便人工浏览的硬链接视图；同一作品进入多个收藏夹时不重复占用空间。
- SQLite 使用 WAL，下载使用 `.part` 断点续传和原子改名。
- 扫码会话和 Cookie 仅保存在 NAS，Cookie 使用 Fernet 加密。

## 运行

```bash
cp .env.example .env
# 填入新生成的 ARCHIVE_MASTER_KEY，并根据 NAS 设置 ARCHIVE_PATH/PUID/PGID
docker compose up -d --build
```

默认访问 `http://NAS-IP:8099` 。首次打开时先创建 NAS 本地管理密码，再扫描页面中的抖音二维码。扫码成功会立即启动首次全量归档，之后每 5 分钟增量同步。

## English

NAS-only permanent archive for Douyin favorite collections. It keeps canonical media in `objects/`, projects collection folders under `library/`, encrypts the retained browser session, and serves a responsive local web viewer.
