import { QrCode, SignOut } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { fetchSettings, updateSettings, type RuntimeSettings } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { formatRelative } from "../lib/format";
import { describeHealth } from "../lib/health";
import { useTheme } from "../theme/theme-context";
import type { ThemePreference } from "../theme/theme-context";
import { Avatar, PageHeader, Segmented, Select } from "../ui/primitives";
import { NotificationsPanel } from "./NotificationsPanel";

const INTERVALS = [120, 300, 600, 900, 1800, 3600];
const WORKERS = [1, 2, 3, 4, 6, 8];

function intervalLabel(seconds: number): string {
  return seconds >= 3600 ? `${seconds / 3600} 小时` : `${Math.round(seconds / 60)} 分钟`;
}

export function SyncSettingsPanel() {
  const { toast, refreshHealth } = useAppData();
  const [values, setValues] = useState<RuntimeSettings | null>(null);
  const [saving, setSaving] = useState<keyof RuntimeSettings | null>(null);

  useEffect(() => {
    let active = true;
    fetchSettings()
      .then((payload) => active && setValues(payload.values))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  async function change<K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) {
    if (!values) return;
    const previous = values;
    setValues({ ...values, [key]: value });
    setSaving(key);
    try {
      const payload = await updateSettings({ [key]: value });
      setValues(payload.values);
      toast("设置已生效");
      void refreshHealth();
    } catch {
      setValues(previous);
      toast("保存失败，请稍后重试");
    } finally {
      setSaving(null);
    }
  }

  const intervals = values && !INTERVALS.includes(values.sync_interval_seconds) ? [values.sync_interval_seconds, ...INTERVALS] : INTERVALS;
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>同步与下载</h2>
        <p>修改后立即生效，不需要重启容器</p>
      </div>
      <div className="setting">
        <div className="setting-text">
          <strong>检查新收藏的间隔</strong>
          <small>太频繁容易触发抖音风控；5 到 15 分钟比较稳妥</small>
        </div>
        <Select
          label="同步间隔"
          value={String(values?.sync_interval_seconds ?? 300)}
          options={intervals.map((seconds) => ({ value: String(seconds), label: intervalLabel(seconds) }))}
          onChange={(value) => void change("sync_interval_seconds", Number(value))}
        />
      </div>
      <div className="setting">
        <div className="setting-text">
          <strong>同时下载的任务数</strong>
          <small>NAS 带宽和磁盘够用时可以调高，默认 2 个</small>
        </div>
        <Select
          label="下载并发数"
          value={String(values?.download_workers ?? 2)}
          options={WORKERS.map((count) => ({ value: String(count), label: `${count} 个` }))}
          onChange={(value) => void change("download_workers", Number(value))}
        />
      </div>
      {saving ? <p className="setting-note">正在保存…</p> : null}
    </section>
  );
}

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

        <SyncSettingsPanel />

        <NotificationsPanel />

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
