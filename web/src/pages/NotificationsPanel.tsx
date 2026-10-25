import { BellRinging, PaperPlaneTilt } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { fetchSettings, testNotifications, updateSettings } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { Spinner, Switch } from "../ui/primitives";
import { t } from "../i18n/t";

type Config = {
  bark: { url: string };
  telegram: { bot_token: string; chat_id: string };
  webhook: { url: string };
  events: Record<string, boolean>;
};

const EVENTS: Array<{ key: string; label: string }> = [
  { key: "login_required", label: t("抖音登录失效") },
  { key: "failing", label: t("同步连续失败") },
  { key: "stale", label: t("同步停止超过半小时") },
  { key: "disk_low", label: t("NAS 剩余空间不足") },
  { key: "recovered", label: t("问题恢复后通知一次") },
];

const EMPTY: Config = { bark: { url: "" }, telegram: { bot_token: "", chat_id: "" }, webhook: { url: "" }, events: {} };

function normalize(raw: Record<string, unknown>): Config {
  const pick = (section: unknown, key: string) => String(((section as Record<string, unknown>) ?? {})[key] ?? "");
  return {
    bark: { url: pick(raw.bark, "url") },
    telegram: { bot_token: pick(raw.telegram, "bot_token"), chat_id: pick(raw.telegram, "chat_id") },
    webhook: { url: pick(raw.webhook, "url") },
    events: { ...((raw.events as Record<string, boolean>) ?? {}) },
  };
}

export function NotificationsPanel() {
  const { toast } = useAppData();
  const [config, setConfig] = useState<Config>(EMPTY);
  const [saved, setSaved] = useState<Config>(EMPTY);
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [results, setResults] = useState<Record<string, string> | null>(null);

  useEffect(() => {
    let active = true;
    fetchSettings()
      .then((payload) => {
        if (!active) return;
        const value = normalize(payload.values.notifications);
        setConfig(value);
        setSaved(value);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const dirty = JSON.stringify(config) !== JSON.stringify(saved);
  const configured = Boolean(config.bark.url || (config.telegram.bot_token && config.telegram.chat_id) || config.webhook.url);

  async function save() {
    setBusy("save");
    try {
      const payload = await updateSettings({ notifications: config });
      const value = normalize(payload.values.notifications);
      setConfig(value);
      setSaved(value);
      toast(t("通知设置已保存"));
    } catch {
      toast(t("保存失败，请检查填写的地址"));
    } finally {
      setBusy(null);
    }
  }

  async function sendTest() {
    setBusy("test");
    setResults(null);
    try {
      if (dirty) await save();
      setResults((await testNotifications()).results);
    } catch {
      toast(t("测试发送失败"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>{t("通知")}</h2>
          <p>{t("登录失效、同步停止时推送到手机，不用天天打开网页检查")}</p>
        </div>
        <BellRinging size={20} className="panel-icon" />
      </div>
      <div className="fields">
        <label className="field">
          <span>{t("Bark 推送地址")}</span>
          <input aria-label={t("Bark 推送地址")} type="url" placeholder={t("https://api.day.app/你的设备Key")} value={config.bark.url} onChange={(event) => setConfig({ ...config, bark: { url: event.target.value } })} />
          <small>{t("iPhone 装 Bark 后，把 App 里显示的地址粘贴到这里")}</small>
        </label>
        <div className="field-row">
          <label className="field">
            <span>Telegram Bot Token</span>
            <input aria-label="Telegram Bot Token" type="text" autoComplete="off" placeholder="123456:ABC…" value={config.telegram.bot_token} onChange={(event) => setConfig({ ...config, telegram: { ...config.telegram, bot_token: event.target.value } })} />
          </label>
          <label className="field">
            <span>Telegram Chat ID</span>
            <input aria-label="Telegram Chat ID" type="text" inputMode="numeric" placeholder={t("例如 123456789")} value={config.telegram.chat_id} onChange={(event) => setConfig({ ...config, telegram: { ...config.telegram, chat_id: event.target.value } })} />
          </label>
        </div>
        <label className="field">
          <span>{t("通用 Webhook")}</span>
          <input aria-label={t("通用 Webhook")} type="url" placeholder={t("https://…（会收到 JSON：event、title、body、level）")} value={config.webhook.url} onChange={(event) => setConfig({ ...config, webhook: { url: event.target.value } })} />
          <small>{t("适合飞书、企业微信、Home Assistant 等自定义接入")}</small>
        </label>
      </div>
      <div className="rows events">
        {EVENTS.map((event) => (
          <div key={event.key} className="row">
            <div className="row-main">
              <strong>{event.label}</strong>
            </div>
            <Switch checked={config.events[event.key] ?? true} onChange={(value) => setConfig({ ...config, events: { ...config.events, [event.key]: value } })} label={event.label} />
          </div>
        ))}
      </div>
      <div className="action-row">
        <button type="button" className="btn btn-primary btn-sm" disabled={!dirty || busy !== null} onClick={() => void save()}>
          {busy === "save" ? <Spinner size={14} /> : null}
          {t("保存")}
        </button>
        <button type="button" className="btn btn-secondary btn-sm" disabled={!configured || busy !== null} onClick={() => void sendTest()}>
          {busy === "test" ? <Spinner size={14} /> : <PaperPlaneTilt size={15} weight="bold" />}
          {t("发送测试")}
        </button>
        {results ? (
          <span className="test-results">
            {Object.entries(results).map(([channel, result]) => (
              <span key={channel} className={`badge ${result === "ok" ? "badge-success" : "badge-danger"}`}>
                {channel} {result === "ok" ? t("已送达") : t("失败")}
              </span>
            ))}
          </span>
        ) : null}
      </div>
    </section>
  );
}
