from datetime import datetime, timezone

import pandas as pd

from moonape import store


def test_append_same_minute_is_idempotent():
    ts = datetime(2026, 10, 23, 15, 7, tzinfo=timezone.utc)
    df = pd.DataFrame({"a": [1, 2, 3]})
    p1 = store.append("stock_bars", df, ts)
    p2 = store.append("stock_bars", df, ts)
    assert p1 == p2
    files = list(store.dataset_dir("stock_bars").glob("dt=*/*.parquet"))
    assert len(files) == 1
    assert len(store.read("stock_bars")) == 3


def test_compact_merges_old_partitions_only():
    df = pd.DataFrame({"a": [1]})
    for h in (13, 14, 15):
        store.append("fred", df, datetime(2026, 10, 22, h, 0, tzinfo=timezone.utc))
    store.append("fred", df, datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc))
    removed = store.compact("fred", before="2026-10-23")
    assert removed == 3
    old = sorted(p.name for p in (store.dataset_dir("fred") / "dt=2026-10-22").glob("*.parquet"))
    assert old == ["all.parquet"]
    assert len(store.read("fred")) == 4  # nothing lost
    assert store.read("fred", "SELECT count(DISTINCT dt) AS n FROM fred").n[0] == 2


def test_latest_dedupes_by_key():
    store.append("reddit_posts", pd.DataFrame({"id": ["x", "y"], "score": [1, 1]}), datetime(2026, 10, 23, 1, tzinfo=timezone.utc))
    store.append("reddit_posts", pd.DataFrame({"id": ["x"], "score": [5]}), datetime(2026, 10, 23, 2, tzinfo=timezone.utc))
    out = store.latest("reddit_posts", "id").set_index("id")
    assert out.loc["x", "score"] == 5 and len(out) == 2


def test_empty_dataset_reads_empty():
    assert store.read("occ_volume").empty
    assert store.summary().rows.sum() == 0
