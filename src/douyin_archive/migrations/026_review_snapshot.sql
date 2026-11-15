-- The collection review is one slow pass over every collected work (about a
-- minute on the NAS), so it is built in the background and read from here.
CREATE TABLE IF NOT EXISTS review_snapshots (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    body_json TEXT NOT NULL,
    built_at INTEGER NOT NULL
);
