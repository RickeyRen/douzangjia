import { DownloadSimple, GithubLogo, QrCode, SignOut } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { fetchSettings, REPO_URL, updateSettings, type RuntimeSettings } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { formatRelative } from "../lib/format";
import { describeHealth } from "../lib/health";
import { useTheme } from "../theme/theme-context";
import type { ThemePreference } from "../theme/theme-context";
import { Avatar, PageHeader, Segmented, Select } from "../ui/primitives";
import { NotificationsPanel } from "./NotificationsPanel";
import { currentLocale, setLocale, t, type Locale } from "../i18n/t";

const INTERVALS = [120, 300, 600, 900, 1800, 3600];
const WORKERS = [1, 2, 3, 4, 6, 8];
const REMOTE_QUOTAS = [0, 50, 200, 500, 1000];

function intervalLabel(seconds: number): string {
  return seconds >= 3600 ? t("{n} 小时", { n: seconds / 3600 }) : t("{n} 分钟", { n: Math.round(seconds / 60) });
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
      toast(t("设置已生效"));
      void refreshHealth();
    } catch {
      setValues(previous);
      toast(t("保存失败，请稍后重试"));
    } finally {
      setSaving(null);
    }
  }

  const intervals = values && !INTERVALS.includes(values.sync_interval_seconds) ? [values.sync_interval_seconds, ...INTERVALS] : INTERVALS;
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{t("同步与下载")}</h2>
        <p>{t("修改后立即生效，不需要重启容器")}</p>
      </div>
      <div className="setting">
        <div className="setting-text">
          <strong>{t("检查新收藏的间隔")}</strong>
          <small>{t("太频繁容易触发抖音风控；5 到 15 分钟比较稳妥")}</small>
        </div>
        <Select
          label={t("同步间隔")}
          value={String(values?.sync_interval_seconds ?? 300)}
          options={intervals.map((seconds) => ({ value: String(seconds), label: intervalLabel(seconds) }))}
          onChange={(value) => void change("sync_interval_seconds", Number(value))}
        />
      </div>
      <div className="setting">
        <div className="setting-text">
          <strong>{t("同时下载的任务数")}</strong>
          <small>{t("NAS 带宽和磁盘够用时可以调高，默认 2 个")}</small>
        </div>
        <Select
          label={t("下载并发数")}
          value={String(values?.download_workers ?? 2)}
          options={WORKERS.map((count) => ({ value: String(count), label: t("{n} 个", { n: count }) }))}
          onChange={(value) => void change("download_workers", Number(value))}
        />
      </div>
      <div className="setting">
        <div className="setting-text">
          <strong>{t("每天抽查多少个作品是否还在抖音上")}</strong>
          <small>{t("发现已删除或设为私密的作品会出现在「已在抖音消失」里；0 表示关闭")}</small>
        </div>
        <Select
          label={t("远端抽查数量")}
          value={String(values?.remote_check_per_day ?? 200)}
          options={REMOTE_QUOTAS.map((count) => ({ value: String(count), label: count === 0 ? t("关闭") : t("{n} 个 / 天", { n: count }) }))}
          onChange={(value) => void change("remote_check_per_day", Number(value))}
        />
      </div>
      {saving ? <p className="setting-note">{t("正在保存…")}</p> : null}
    </section>
  );
}

const ACCOUNT_STATUS: Record<string, { text: string; tone: string }> = {
  healthy: { text: t("已连接"), tone: "badge-success" },
  checking: { text: t("检查中"), tone: "badge-info" },
  degraded: { text: t("连接不稳定"), tone: "badge-warning" },
  expired: { text: t("登录已失效"), tone: "badge-danger" },
  unknown: { text: t("状态未知"), tone: "" },
};

export function SettingsPage() {
  const { account, health, requestDouyinLogin, logoutDouyin, logout, about, toast } = useAppData();
  const [leavingDouyin, setLeavingDouyin] = useState(false);

  async function leaveDouyin() {
    if (!window.confirm(t("退出抖音登录？之后需要重新扫码，同步才会继续。"))) return;
    setLeavingDouyin(true);
    try {
      await logoutDouyin();
    } catch {
      toast(t("退出失败，请稍后重试"));
    } finally {
      setLeavingDouyin(false);
    }
  }
  const { preference, setPreference } = useTheme();
  const status = ACCOUNT_STATUS[account?.status ?? "unknown"] ?? ACCOUNT_STATUS.unknown;
  const nickname = account?.account?.nickname;
  const view = describeHealth(health);

  return (
    <>
      <PageHeader title={t("设置")} />
      <div className="settings">
        <section className="panel">
          <div className="panel-head">
            <h2>{t("抖音账号")}</h2>
            <span className={`badge ${status.tone}`}>{status.text}</span>
          </div>
          <div className="account">
            <Avatar src={account?.account?.avatarUrl} name={nickname ?? t("抖")} />
            <div className="health-text">
              <strong>{nickname ?? t("未获取到昵称")}</strong>
              <small>
                {account?.account?.uniqueId ? t("抖音号 {id} · ", { id: account.account.uniqueId }) : ""}
                上次验证 {formatRelative(account?.lastVerifiedAt)}
              </small>
            </div>
            <div className="account-actions">
              <button type="button" className="btn btn-secondary btn-sm" onClick={requestDouyinLogin}>
                <QrCode size={16} weight="bold" />
                {t("重新扫码")}
              </button>
              <button type="button" className="btn btn-ghost btn-sm" onClick={() => void leaveDouyin()} disabled={leavingDouyin}>
                <SignOut size={16} weight="bold" />
                {t("退出抖音登录")}
              </button>
            </div>
          </div>
          <p className="setting-note">{t("登录信息只保存在这台 NAS 上，浏览器档案和加密的 Cookie 不会离开你的网络。")}{view.alert ? t(" 当前状态：{title}。", { title: view.title }) : ""}</p>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>{t("外观")}</h2>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>{t("主题")}</strong>
              <small>{t("深色更适合看视频，也可以跟随系统自动切换")}</small>
            </div>
            <Segmented<ThemePreference>
              label={t("主题")}
              value={preference}
              options={[
                { value: "dark", label: t("深色") },
                { value: "light", label: t("浅色") },
                { value: "system", label: t("跟随系统") },
              ]}
              onChange={setPreference}
            />
          </div>
        </section>

        <SyncSettingsPanel />

        <NotificationsPanel />

        <section className="panel">
          <div className="panel-head">
            <h2>{t("语言")}</h2>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>{t("语言")}</strong>
              <small>{t("切换语言后页面会重新加载")}</small>
            </div>
            <Segmented<Locale>
              label={t("语言")}
              value={currentLocale()}
              options={[
                { value: "zh-CN", label: "中文" },
                { value: "en", label: "English" },
              ]}
              onChange={(value) => {
                setLocale(value);
                window.location.reload();
              }}
            />
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>{t("归档规则")}</h2>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>{t("只增不删")}</strong>
              <small>{t("在抖音取消收藏、作者删除或设为私密，已经存到 NAS 的文件都不会被删除。")}</small>
            </div>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>{t("按收藏夹整理")}</strong>
              <small>{t("原文件保存在 objects/ 目录，library/ 下按收藏夹名称建立硬链接，同一作品不重复占用空间。")}</small>
            </div>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>{t("精选只在本地")}</strong>
              <small>{t("精选标记保存在 NAS 的数据库里，不会改动你在抖音上的收藏。")}</small>
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>{t("数据与备份")}</h2>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>{t("下载数据库备份")}</strong>
              <small>{t("收藏记录、相册、标签、备注和精选都在这一个文件里；媒体文件在归档目录的 objects/ 下，请用 NAS 自己的备份工具。")}</small>
            </div>
            <a className="btn btn-secondary btn-sm" href="/api/backup/database" download>
              <DownloadSimple size={15} weight="bold" />
              {t("下载")}
            </a>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>{t("关于")}</h2>
            <span className="badge num">v{about.version}</span>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>{t("抖藏家")}</strong>
              <small>
                {t("版本 {version}", { version: about.version })}
                {about.commit && about.commit !== "unknown" ? t(" · 构建 {commit}", { commit: about.commit.slice(0, 7) }) : ""}{t(" · MIT 开源")}
              </small>
            </div>
            <a className="btn btn-ghost btn-sm" href={REPO_URL} target="_blank" rel="noreferrer">
              <GithubLogo size={16} weight="bold" />
              GitHub
            </a>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>{t("本机登录")}</h2>
          </div>
          <div className="setting">
            <div className="setting-text">
              <strong>{t("退出抖藏家")}</strong>
              <small>{t("只退出这个浏览器上的管理员登录，不影响抖音账号和后台同步。")}</small>
            </div>
            <button type="button" className="btn btn-danger btn-sm" onClick={logout}>
              <SignOut size={16} weight="bold" />
              {t("退出登录")}
            </button>
          </div>
        </section>
      </div>
    </>
  );
}
