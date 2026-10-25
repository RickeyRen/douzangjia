import { Check, FolderPlus, Plus, X } from "@phosphor-icons/react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { addToAlbum, createAlbum, removeFromAlbum, setItemNote, setItemTags, type FeedItem } from "../app/api";
import { useAppData } from "../app/appDataContext";
import { Spinner } from "../ui/primitives";
import { t } from "../i18n/t";

/** Checkbox list of albums for one or many items, with inline creation. */
export function AlbumPicker({
  itemIds,
  selected,
  onChange,
  onClose,
}: {
  itemIds: string[];
  /** Album ids the (single) item is already in; omitted for bulk use. */
  selected?: number[];
  onChange?: (albumId: number, member: boolean, name: string) => void;
  onClose: () => void;
}) {
  const { albums, refreshAlbums, toast } = useAppData();
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<number | "new" | null>(null);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (creating) input.current?.focus();
  }, [creating]);

  async function toggle(albumId: number, albumName: string) {
    const member = selected?.includes(albumId) ?? false;
    setBusy(albumId);
    try {
      if (member) await removeFromAlbum(albumId, itemIds);
      else await addToAlbum(albumId, itemIds);
      onChange?.(albumId, !member, albumName);
      toast(member ? t("已从「{name}」移除", { name: albumName }) : t("已加入「{name}」", { name: albumName }));
      void refreshAlbums();
    } catch {
      toast(t("操作失败，请稍后重试"));
    } finally {
      setBusy(null);
    }
  }

  async function create() {
    const value = name.trim();
    if (!value) return;
    setBusy("new");
    try {
      const album = await createAlbum(value);
      await addToAlbum(album.id, itemIds);
      onChange?.(album.id, true, album.name);
      toast(t("已创建「{name}」并加入", { name: album.name }));
      void refreshAlbums();
      setName("");
      setCreating(false);
    } catch {
      toast(t("创建相册失败，可能已有同名相册"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="popover" role="dialog" aria-label={t("加入相册")}>
      <div className="popover-head">
        <strong>{itemIds.length > 1 ? t("把 {n} 个作品加入相册", { n: itemIds.length }) : t("加入相册")}</strong>
        <button type="button" className="icon-btn icon-btn-sm" aria-label={t("关闭")} onClick={onClose}>
          <X size={14} />
        </button>
      </div>
      <div className="popover-list">
        {albums.length === 0 && !creating ? <p className="empty-note">{t("还没有相册，先创建一个。")}</p> : null}
        {albums.map((album) => {
          const member = selected?.includes(album.id) ?? false;
          return (
            <button key={album.id} type="button" className="popover-item" aria-pressed={member} disabled={busy !== null} onClick={() => void toggle(album.id, album.name)}>
              <span className={`check${member ? " is-on" : ""}`}>{busy === album.id ? <Spinner size={12} /> : member ? <Check size={12} weight="bold" /> : null}</span>
              <span className="popover-item-text">{album.name}</span>
              <small>{album.itemCount}</small>
            </button>
          );
        })}
      </div>
      {creating ? (
        <form
          className="popover-create"
          onSubmit={(event) => {
            event.preventDefault();
            void create();
          }}
        >
          <input ref={input} aria-label={t("新相册名称")} placeholder={t("相册名称")} maxLength={60} value={name} onChange={(event) => setName(event.target.value)} />
          <button type="submit" className="btn btn-primary btn-sm" disabled={!name.trim() || busy === "new"}>
            {busy === "new" ? <Spinner size={14} /> : t("创建")}
          </button>
        </form>
      ) : (
        <button type="button" className="popover-footer" onClick={() => setCreating(true)}>
          <FolderPlus size={16} />
          {t("新建相册")}
        </button>
      )}
    </div>
  );
}

export function TagEditor({ item, onChange }: { item: FeedItem; onChange: (tags: string[]) => void }) {
  const { toast } = useAppData();
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const tags = item.tags ?? [];

  async function commit(next: string[]) {
    setSaving(true);
    try {
      const result = await setItemTags(item.awemeId, next);
      onChange(result.tags);
    } catch {
      toast(t("标签保存失败"));
    } finally {
      setSaving(false);
    }
  }

  function onKey(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      const value = draft.replace(/[#,]/g, "").trim();
      if (!value || tags.includes(value)) {
        setDraft("");
        return;
      }
      setDraft("");
      void commit([...tags, value]);
    } else if (event.key === "Backspace" && !draft && tags.length) {
      void commit(tags.slice(0, -1));
    }
  }

  return (
    <div className="tag-editor">
      {tags.map((tag) => (
        <span key={tag} className="tag-chip">
          #{tag}
          <button type="button" aria-label={t("移除标签 {tag}", { tag })} onClick={() => void commit(tags.filter((entry) => entry !== tag))}>
            <X size={11} weight="bold" />
          </button>
        </span>
      ))}
      <input
        aria-label={t("添加标签")}
        placeholder={tags.length ? t("继续添加…") : t("输入标签，回车添加")}
        value={draft}
        disabled={saving}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKey}
        onBlur={() => {
          const value = draft.replace(/[#,]/g, "").trim();
          if (value && !tags.includes(value)) void commit([...tags, value]);
          setDraft("");
        }}
      />
      {saving ? <Spinner size={12} /> : null}
    </div>
  );
}

export function NoteEditor({ item, onChange }: { item: FeedItem; onChange: (note: string | null) => void }) {
  const { toast } = useAppData();
  const [draft, setDraft] = useState(item.note ?? "");
  const [saving, setSaving] = useState(false);
  useEffect(() => setDraft(item.note ?? ""), [item.awemeId, item.note]);

  async function save() {
    if ((item.note ?? "") === draft.trim()) return;
    setSaving(true);
    try {
      const result = await setItemNote(item.awemeId, draft);
      onChange(result.note);
    } catch {
      toast(t("备注保存失败"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="note-editor">
      <textarea aria-label={t("备注")} placeholder={t("写点什么，只有你能看到")} rows={3} maxLength={4000} value={draft} onChange={(event) => setDraft(event.target.value)} onBlur={() => void save()} />
      {saving ? <Spinner size={12} /> : null}
    </div>
  );
}

export function AddToAlbumButton({ item, onItemPatch }: { item: FeedItem; onItemPatch: (patch: Partial<FeedItem>) => void }) {
  const [open, setOpen] = useState(false);
  const selected = (item.albums ?? []).map((album) => album.id);
  return (
    <span className="popover-anchor">
      <button type="button" className={`panel-action${selected.length ? " is-active" : ""}`} aria-expanded={open} onClick={() => setOpen((value) => !value)}>
        <Plus size={20} />
        {selected.length ? t("相册 {n}", { n: selected.length }) : t("加入相册")}
      </button>
      {open ? (
        <AlbumPicker
          itemIds={[item.awemeId]}
          selected={selected}
          onClose={() => setOpen(false)}
          onChange={(albumId, member, name) => {
            const current = item.albums ?? [];
            onItemPatch({ albums: member ? [...current.filter((album) => album.id !== albumId), { id: albumId, name }] : current.filter((album) => album.id !== albumId) });
          }}
        />
      ) : null}
    </span>
  );
}
