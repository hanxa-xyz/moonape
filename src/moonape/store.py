"""Append-only parquet store with daily compaction and DuckDB views.

Layout: data/<dataset>/dt=YYYY-MM-DD/HHMM.parquet  (one file per run; a re-run of the same minute overwrites)
Compaction merges a day's files into data/<dataset>/dt=YYYY-MM-DD/all.parquet, so the glob never changes.
Every row carries `fetched_at` (UTC). Slowly changing datasets (reddit posts, filings) are appended on every
fetch and de-duplicated at read time with `latest()`.
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

from moonape import config

log = logging.getLogger("moonape.store")

DATASETS = [
    "stock_snapshots", "stock_bars", "option_contracts", "option_chain", "chain_metrics",
    "macro_intraday", "treasury_curve", "fred", "reddit_posts", "edgar_filings", "edgar_13f",
    "finra_short_volume", "occ_volume", "social_posts", "library_books", "library_text",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _root() -> Path:
    return Path(config.DATA)


def dataset_dir(dataset: str) -> Path:
    return _root() / dataset


def glob(dataset: str) -> str:
    return str(dataset_dir(dataset) / "dt=*" / "*.parquet")


def exists(dataset: str) -> bool:
    d = dataset_dir(dataset)
    return d.is_dir() and any(d.glob("dt=*/*.parquet"))


def append(dataset: str, df: pd.DataFrame, ts: datetime | None = None, name: str | None = None) -> Path | None:
    """Write df as one parquet file under today's partition. Returns the path, or None for an empty frame."""
    if df is None or len(df) == 0:
        log.info("%s: nothing to write", dataset)
        return None
    ts = ts or utcnow()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    df = df.copy()
    if "fetched_at" not in df.columns:
        df["fetched_at"] = ts
    part = dataset_dir(dataset) / f"dt={ts:%Y-%m-%d}"
    part.mkdir(parents=True, exist_ok=True)
    path = part / f"{name or ts.strftime('%H%M')}.parquet"
    df.to_parquet(path, compression="zstd", index=False)
    log.info("%s: wrote %d rows → %s", dataset, len(df), path.relative_to(_root()))
    return path


def compact(dataset: str, before: str | None = None) -> int:
    """Merge every partition older than `before` (YYYY-MM-DD, default today UTC) into all.parquet. Returns files removed."""
    before = before or utcnow().strftime("%Y-%m-%d")
    removed = 0
    d = dataset_dir(dataset)
    if not d.is_dir():
        return 0
    for part in sorted(d.glob("dt=*")):
        dt = part.name[3:]
        if dt >= before:
            continue
        files = sorted(part.glob("*.parquet"))
        if len(files) <= 1 and (not files or files[0].name == "all.parquet"):
            continue
        frames = [pd.read_parquet(f) for f in files]
        merged = pd.concat(frames, ignore_index=True)
        tmp = part / "all.parquet.tmp"
        merged.to_parquet(tmp, compression="zstd", index=False)
        for f in files:
            f.unlink()
            removed += 1
        shutil.move(str(tmp), str(part / "all.parquet"))
        log.info("%s: compacted %s (%d files → 1, %d rows)", dataset, dt, len(files), len(merged))
    return removed


def compact_all(before: str | None = None) -> int:
    return sum(compact(ds, before) for ds in DATASETS)


def connect() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with one view per dataset that has files. Missing datasets are simply absent."""
    con = duckdb.connect()
    for ds in DATASETS:
        if exists(ds):
            con.execute(f"CREATE VIEW {ds} AS SELECT * FROM read_parquet('{glob(ds)}', hive_partitioning=true, union_by_name=true)")
    return con


def read(dataset: str, sql: str | None = None, con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    """Whole dataset, or a SQL statement that references it. Empty frame when there are no files."""
    if not exists(dataset):
        return pd.DataFrame()
    own = con is None
    con = con or connect()
    try:
        return con.execute(sql or f"SELECT * FROM {dataset}").df()
    finally:
        if own:
            con.close()


def latest(dataset: str, key: str, order: str = "fetched_at", con=None) -> pd.DataFrame:
    """One row per key: the most recently fetched version (for append-only slowly-changing datasets)."""
    if not exists(dataset):
        return pd.DataFrame()
    sql = f"SELECT * FROM {dataset} QUALIFY row_number() OVER (PARTITION BY {key} ORDER BY {order} DESC) = 1"
    return read(dataset, sql, con)


def summary() -> pd.DataFrame:
    rows = []
    for ds in DATASETS:
        if not exists(ds):
            rows.append({"dataset": ds, "rows": 0, "partitions": 0, "latest_fetch": None, "mb": 0.0})
            continue
        files = list(dataset_dir(ds).glob("dt=*/*.parquet"))
        mb = sum(f.stat().st_size for f in files) / 1e6
        df = read(ds, f"SELECT count(*) AS n, max(fetched_at) AS latest FROM {ds}")
        rows.append({"dataset": ds, "rows": int(df.n[0]), "partitions": len({f.parent for f in files}),
                     "latest_fetch": df.latest[0], "mb": round(mb, 2)})
    return pd.DataFrame(rows)
