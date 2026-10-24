import { QrCode, SignOut } from "@phosphor-icons/react";

import { useAppData } from "../app/appDataContext";
import { formatRelative } from "../lib/format";
import { describeHealth } from "../lib/health";
import { useTheme } from "../theme/theme-context";
import type { ThemePreference } from "../theme/theme-context";
import { Avatar, PageHeader, Segmented } from "../ui/primitives";

const ACCOUNT_STATUS: Record<string, { text: string; tone: string }> = {
  healthy: { text: "已连接", tone: "badge-success" },
  checking: { text: "检查中", tone: "badge-info" },
  degraded: { text: "连接不稳定", tone: "badge-warning" },
  expired: { text: "登录已失效", tone: "badge-danger" },
  unknown: { text: "状态未知", tone: "" },
};

export function SettingsPage() {
  const { account, health, requestDouyinLogin, logout } = useAppData();
  const { preference, setPreference } = useTheme();
  const status = ACCOUNT_STATUS[account?.status ?? "unknown"] ?? ACCOUNT_STATUS.unknown;
  const nickname = account?.account?.nickname;
  const view = describeHealth(health);

  return (
    <>
      <PageHeader title="设置" />
      <div className="settings">
        <section className="panel">
          <div className="panel-head">
            <h2>抖音账号</h2>
            <span className={`badge ${status.tone}`}>{status.text}</span>
          </div>
          <div className="account">
            <Avatar src={account?.account?.avatarUrl} name={nickname ?? "抖"} />
            <div className="health-text">
              <strong>{nickname ?? "未获取到昵称"}</strong>
              <small>
                {account?.account?.uniqueId ? `抖音号 ${account.account.uniqueId} · ` : ""}
                上次验证 {formatRelative(account?.lastVerifiedAt)}
              </small>
            </div>
            <button type="button" className="btn btn-secondary btn-sm" onClick={requestDouyinLogin}>
              <QrCode size={16} weight="bold" />
              重新扫码
            </button>
          </div>
          <p className="setting-note">登录信息只保存在这台 NAS 上，浏览器档案和加密的 Cookie 不会离开你的网络。{view.alert ? ` 当前状态：${view.title}。` : ""}</p>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>外观</h2>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>主题</strong>
              <small>深色更适合看视频，也可以跟随系统自动切换</small>
            </div>
            <Segmented<ThemePreference>
              label="主题"
              value={preference}
              options={[
                { value: "dark", label: "深色" },
                { value: "light", label: "浅色" },
                { value: "system", label: "跟随系统" },
              ]}
              onChange={setPreference}
            />
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>归档规则</h2>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>只增不删</strong>
              <small>在抖音取消收藏、作者删除或设为私密，已经存到 NAS 的文件都不会被删除。</small>
            </div>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>按收藏夹整理</strong>
              <small>原文件保存在 objects/ 目录，library/ 下按收藏夹名称建立硬链接，同一作品不重复占用空间。</small>
            </div>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>精选只在本地</strong>
              <small>精选标记保存在 NAS 的数据库里，不会改动你在抖音上的收藏。</small>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>本机登录</h2>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>退出抖藏家</strong>
              <small>只退出这个浏览器上的管理员登录，不影响抖音账号和后台同步。</small>
            </div>
            <button type="button" className="btn btn-danger btn-sm" onClick={logout}>
              <SignOut size={16} weight="bold" />
              退出登录
            </button>
          </div>
        </section>
      </div>
    </>
  );
}
