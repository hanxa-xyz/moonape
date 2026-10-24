"""The SuperStonk Library: a public FlipHTML5 bookcase (250 books of community DD, art books, periodicals).

The bookcase listing page is behind Cloudflare for scripts, so it is captured once from a browser into library/bookcase.json
(refresh when the shelf changes; it moves a few times a year). Each book's page text comes from the flipbook's own search
index, files/search/search_config.js, which is public, keyless and not disallowed by robots.txt. Covers: files/shot.jpg.
Text is stored for search and excerpts only; the page links out to the flipbook rather than republishing it.
"""
from __future__ import annotations

import json
import logging
import re

import pandas as pd

from moonape import config
from moonape.http import Http

log = logging.getLogger("moonape.library")
BOOK_URL = "https://online.fliphtml5.com/{ulink}/{blink}/"
TEXT_URL = "https://online.fliphtml5.com/{ulink}/{blink}/files/search/search_config.js"
COVER_URL = "https://online.fliphtml5.com/{ulink}/{blink}/files/shot.jpg"
BOOK_COLS = ["book_id", "blink", "title", "description", "pages", "added", "updated", "url", "cover", "curated_rank"]


def load_bookcase(path=None) -> pd.DataFrame:
    """library/bookcase.json rows: [id, bLink, title, description, pages, newTime, updateTime]."""
    p = path or config.LIBRARY_BOOKCASE_FILE
    rows = json.loads(open(p, encoding="utf-8").read())
    df = pd.DataFrame(rows, columns=["book_id", "blink", "title", "description", "pages", "added", "updated"])
    df["url"] = [BOOK_URL.format(ulink=config.LIBRARY_ULINK, blink=b) for b in df["blink"]]
    df["cover"] = [COVER_URL.format(ulink=config.LIBRARY_ULINK, blink=b) for b in df["blink"]]
    df["curated_rank"] = [_curated_rank(t) for t in df["title"]]
    df["added"] = pd.to_datetime(df["added"]).dt.date
    df["updated"] = pd.to_datetime(df["updated"]).dt.date
    return df[BOOK_COLS]


def _curated_rank(title: str):
    for i, key in enumerate(config.LIBRARY_CURATED):
        if key.lower() in (title or "").lower():
            return i
    return None


def fetch_text(http: Http, blink: str) -> list[str]:
    """One string per page (empty for image-only pages)."""
    r = http.get(TEXT_URL.format(ulink=config.LIBRARY_ULINK, blink=blink), headers={"User-Agent": "Mozilla/5.0"}, fixture=f"library/{blink}_search_config",
                 ok_404=True)
    if getattr(r, "status_code", 200) == 404:
        return []
    src = r.text.lstrip("﻿")
    m = re.search(r"var\s+textForPages\s*=\s*\[", src)
    start = m.end() - 1 if m else src.find("[")
    if start < 0:
        return []
    try:  # decode exactly one JSON array; the file continues with `; var positionForPages = …`
        pages, _ = json.JSONDecoder(strict=False).raw_decode(src, start)
    except json.JSONDecodeError as e:
        log.warning("library %s: text layer not parseable (%s)", blink, e)
        return []
    return [_clean(p) for p in pages if isinstance(p, str) or p is None]


_LONE_SURROGATE = re.compile(r"[\ud800-\udfff]")


def _clean(page: str | None) -> str:
    """Collapse whitespace and drop lone UTF-16 surrogates (FlipHTML5 escapes emoji as split pairs), which parquet cannot encode."""
    return re.sub(r"\s+", " ", _LONE_SURROGATE.sub("", page or "")).strip()


def excerpt(pages: list[str], n: int = 500) -> str:
    for p in pages:
        if len(p) >= 200:
            return p[:n].rsplit(" ", 1)[0] + ("…" if len(p) > n else "")
    joined = " ".join(p for p in pages if p)
    return (joined[:n] + "…") if len(joined) > n else joined


def fetch_books_text(http: Http, blinks: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """→ (per-book stats with excerpt, per-page text rows)."""
    stats, text_rows = [], []
    for b in blinks:
        try:
            pages = fetch_text(http, b)
        except FileNotFoundError:
            continue
        except Exception as e:
            log.warning("library %s text failed: %s", b, e)
            continue
        non_empty = [p for p in pages if p]
        stats.append({"blink": b, "text_pages": len(non_empty), "text_chars": sum(len(p) for p in pages), "excerpt": excerpt(pages), "text_fetched": True})
        text_rows.extend({"blink": b, "page": i + 1, "text": p} for i, p in enumerate(pages) if p)
    return pd.DataFrame(stats), pd.DataFrame(text_rows, columns=["blink", "page", "text"])
