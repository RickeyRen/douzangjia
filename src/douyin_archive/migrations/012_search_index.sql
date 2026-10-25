CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    remote_id UNINDEXED,
    description,
    author,
    creator,
    hashtags,
    tags,
    note,
    tokenize='trigram'
);

INSERT INTO items_fts (remote_id, description, author, creator, hashtags, tags, note)
SELECT
    i.remote_id,
    i.description,
    i.author_name,
    COALESCE((SELECT c.nickname || ' ' || COALESCE(c.unique_id, '') FROM creators c WHERE c.remote_id = i.creator_id), ''),
    COALESCE(json_extract(i.metadata_json, '$.hashtags'), ''),
    COALESCE((SELECT group_concat(t.tag, ' ') FROM item_tags t WHERE t.item_id = i.remote_id), ''),
    COALESCE((SELECT n.note FROM item_notes n WHERE n.item_id = i.remote_id), '')
FROM items i;

CREATE TRIGGER IF NOT EXISTS items_fts_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts (remote_id, description, author, creator, hashtags, tags, note)
    VALUES (
        new.remote_id, new.description, new.author_name,
        COALESCE((SELECT c.nickname || ' ' || COALESCE(c.unique_id, '') FROM creators c WHERE c.remote_id = new.creator_id), ''),
        COALESCE(json_extract(new.metadata_json, '$.hashtags'), ''),
        '', ''
    );
END;

CREATE TRIGGER IF NOT EXISTS items_fts_au AFTER UPDATE OF description, author_name, creator_id, metadata_json ON items BEGIN
    UPDATE items_fts SET
        description = new.description,
        author = new.author_name,
        creator = COALESCE((SELECT c.nickname || ' ' || COALESCE(c.unique_id, '') FROM creators c WHERE c.remote_id = new.creator_id), ''),
        hashtags = COALESCE(json_extract(new.metadata_json, '$.hashtags'), '')
    WHERE remote_id = new.remote_id;
END;

CREATE TRIGGER IF NOT EXISTS items_fts_ad AFTER DELETE ON items BEGIN
    DELETE FROM items_fts WHERE remote_id = old.remote_id;
END;

CREATE TRIGGER IF NOT EXISTS items_fts_tags_ai AFTER INSERT ON item_tags BEGIN
    UPDATE items_fts SET tags = COALESCE((SELECT group_concat(t.tag, ' ') FROM item_tags t WHERE t.item_id = new.item_id), '')
    WHERE remote_id = new.item_id;
END;

CREATE TRIGGER IF NOT EXISTS items_fts_tags_ad AFTER DELETE ON item_tags BEGIN
    UPDATE items_fts SET tags = COALESCE((SELECT group_concat(t.tag, ' ') FROM item_tags t WHERE t.item_id = old.item_id), '')
    WHERE remote_id = old.item_id;
END;

CREATE TRIGGER IF NOT EXISTS items_fts_note_ai AFTER INSERT ON item_notes BEGIN
    UPDATE items_fts SET note = new.note WHERE remote_id = new.item_id;
END;

CREATE TRIGGER IF NOT EXISTS items_fts_note_au AFTER UPDATE ON item_notes BEGIN
    UPDATE items_fts SET note = new.note WHERE remote_id = new.item_id;
END;

CREATE TRIGGER IF NOT EXISTS items_fts_note_ad AFTER DELETE ON item_notes BEGIN
    UPDATE items_fts SET note = '' WHERE remote_id = old.item_id;
END;

CREATE TRIGGER IF NOT EXISTS items_fts_creator_au AFTER UPDATE OF nickname, unique_id ON creators BEGIN
    UPDATE items_fts SET creator = new.nickname || ' ' || COALESCE(new.unique_id, '')
    WHERE remote_id IN (SELECT remote_id FROM items WHERE creator_id = new.remote_id);
END;
