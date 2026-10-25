import { X } from "@phosphor-icons/react";
import { useEffect } from "react";

const GROUPS: Array<{ title: string; rows: Array<[string[], string]> }> = [
  {
    title: "任何页面",
    rows: [
      [["/"], "聚焦搜索框"],
      [["⌘", "K"], "打开命令面板，跳到任何收藏夹、相册或博主"],
      [["?"], "显示这个快捷键列表"],
      [["Esc"], "关闭面板或退出选择"],
    ],
  },
  {
    title: "网格",
    rows: [
      [["Shift", "点击"], "选择模式下按范围选中"],
      [["⌘", "A"], "选择模式下全选已加载的作品"],
    ],
  },
  {
    title: "播放器",
    rows: [
      [["↑", "↓"], "上一个 / 下一个（J / K 也可以）"],
      [["←", "→"], "图集翻页；到头后切换作品"],
      [["空格"], "播放 / 暂停"],
      [["S"], "加入或取消精选"],
      [["M"], "静音"],
      [["I"], "显示或收起详情面板"],
      [["F"], "全屏"],
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
      <div className="modal" role="dialog" aria-modal="true" aria-label="快捷键" onClick={(event) => event.stopPropagation()}>
        <div className="modal-head">
          <h2>快捷键</h2>
          <button type="button" className="icon-btn icon-btn-sm" aria-label="关闭" onClick={onClose}>
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
