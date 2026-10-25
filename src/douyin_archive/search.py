from __future__ import annotations

TRIGRAM_MIN = 3


def fts_query(term: str) -> str | None:
    """Build an FTS5 MATCH expression, or None when a token is too short for trigrams."""
    tokens = [token for token in term.split() if token]
    if not tokens or any(len(token) < TRIGRAM_MIN for token in tokens):
        return None
    return " AND ".join('"' + token.replace('"', '""') + '"' for token in tokens)


def search_clause(term: str, *, alias: str = "i") -> tuple[str, list[object], bool]:
    """Return (sql, params, uses_fts) restricting rows to those matching every token."""
    query = fts_query(term)
    if query is not None:
        return (
            f"{alias}.remote_id IN (SELECT remote_id FROM items_fts WHERE items_fts MATCH ?)",
            [query],
            True,
        )
    tokens = [token for token in term.split() if token] or [term]
    pieces: list[str] = []
    params: list[object] = []
    for token in tokens:
        like = f"%{token}%"
        pieces.append(
            f"({alias}.description LIKE ? OR {alias}.author_name LIKE ? OR {alias}.remote_id LIKE ? "
            f"OR EXISTS (SELECT 1 FROM creators c WHERE c.remote_id={alias}.creator_id "
            "AND (c.nickname LIKE ? OR c.unique_id LIKE ?)) "
            f"OR EXISTS (SELECT 1 FROM item_tags it WHERE it.item_id={alias}.remote_id AND it.tag LIKE ?) "
            f"OR EXISTS (SELECT 1 FROM item_notes n WHERE n.item_id={alias}.remote_id AND n.note LIKE ?))"
        )
        params.extend([like] * 7)
    return " AND ".join(pieces), params, False


RELEVANCE_SQL = (
    "(SELECT -bm25(items_fts, 0, 4.0, 3.0, 2.0, 2.0, 3.0, 1.0) FROM items_fts "
    "WHERE items_fts.remote_id={alias}.remote_id AND items_fts MATCH ?)"
)
