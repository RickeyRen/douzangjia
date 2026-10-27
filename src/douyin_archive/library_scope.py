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
