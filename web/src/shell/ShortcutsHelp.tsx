import { X } from "@phosphor-icons/react";
import { useEffect } from "react";
import { t } from "../i18n/t";

const GROUPS: Array<{ title: string; rows: Array<[string[], string]> }> = [
  {
    title: t("任何页面"),
    rows: [
      [["/"], t("聚焦搜索框")],
      [["⌘", "K"], t("打开命令面板，跳到任何收藏夹、相册或博主")],
      [["?"], t("显示这个快捷键列表")],
      [["Esc"], t("关闭面板或退出选择")],
    ],
  },
  {
    title: t("网格"),
    rows: [
      [["Shift", t("点击")], t("选择模式下按范围选中")],
      [["⌘", "A"], t("选择模式下全选已加载的作品")],
    ],
  },
  {
    title: t("播放器"),
    rows: [
      [["↑", "↓"], t("上一个 / 下一个（J / K 也可以）")],
      [["←", "→"], t("图集翻页；到头后切换作品")],
      [[t("空格")], t("播放 / 暂停")],
      [["S"], t("加入或取消精选")],
      [["M"], t("静音")],
      [["I"], t("显示或收起详情面板")],
      [["F"], t("全屏")],
    ],
  },
];

export function ShortcutsHelp({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="scrim" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={t("快捷键")} onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h2>{t("快捷键")}</h2>
          <button type="button" className="icon-btn icon-btn-sm" aria-label={t("关闭")} onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <div className="shortcut-groups">
          {GROUPS.map((group) => (
            <section key={group.title}>
              <h3>{group.title}</h3>
              {group.rows.map(([keys, label]) => (
                <div key={label} className="shortcut-row">
                  <span className="shortcut-keys">
                    {keys.map((key) => (
                      <span key={key} className="kbd">
                        {key}
                      </span>
                    ))}
                  </span>
                  <span>{label}</span>
                </div>
              ))}
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
