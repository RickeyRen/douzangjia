from __future__ import annotations

# The recommend feed and watch history are snapshots of what Douyin showed,
# not things the user chose to keep; their stale entries outlive the snapshot
# in `items` but must not inflate the library or the "save everything" scope.
TRANSIENT_SOURCE_KINDS = ("recommend", "watch_history")


def library_item_sql(alias: str = "i") -> str:
    """SQL predicate: the item belongs to the user's library, not a passing feed."""
    transient = ", ".join(f"'{kind}'" for kind in TRANSIENT_SOURCE_KINDS)
    return (
        "("
        f"EXISTS (SELECT 1 FROM source_items lsi JOIN library_sources lls ON lls.id=lsi.source_id "
        f"WHERE lsi.item_id={alias}.remote_id AND lls.kind NOT IN ({transient})) "
        f"OR EXISTS (SELECT 1 FROM media_files lmf WHERE lmf.item_id={alias}.remote_id "
        "AND lmf.status='ready') "
        f"OR EXISTS (SELECT 1 FROM item_stars lst WHERE lst.item_id={alias}.remote_id) "
        f"OR EXISTS (SELECT 1 FROM album_items lai WHERE lai.item_id={alias}.remote_id) "
        f"OR EXISTS (SELECT 1 FROM download_jobs ldj WHERE ldj.kind='download' "
        f"AND ldj.remote_id={alias}.remote_id)"
        ")"
    )


def library_item_ids_sql() -> str:
    """SQL listing every library item id once; same rule as library_item_sql.

    Each branch is an index-only scan of a small table, so callers that need the
    whole library can avoid running five EXISTS probes for every item row.
    """
    transient = ", ".join(f"'{kind}'" for kind in TRANSIENT_SOURCE_KINDS)
    return (
        "SELECT lsi.item_id FROM source_items lsi JOIN library_sources lls "
        f"ON lls.id=lsi.source_id WHERE lls.kind NOT IN ({transient}) "
        "UNION SELECT item_id FROM media_files WHERE status='ready' "
        "UNION SELECT item_id FROM item_stars "
        "UNION SELECT item_id FROM album_items "
        "UNION SELECT remote_id FROM download_jobs WHERE kind='download'"
    )
