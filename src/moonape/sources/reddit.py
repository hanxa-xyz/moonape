"""r/Superstonk posts: Reddit OAuth (script app, app-only token) when credentials exist, else Arctic Shift (keyless).

Reddit shut unauthenticated .json endpoints in May 2026. Both clients return the same columns.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from moonape import config
from moonape.http import Http

log = logging.getLogger("moonape.reddit")
ARCTIC = "https://arctic-shift.photon-reddit.com/api/posts/search"
COLS = ["id", "created_utc", "title", "author", "flair", "score", "num_comments", "upvote_ratio", "url", "permalink",
        "selftext", "is_self", "domain", "over_18", "source"]


def _normalize(posts: list[dict], source: str) -> pd.DataFrame:
    rows = []
    for p in posts:
        pl = p.get("permalink") or ""
        rows.append({
            "id": p.get("id"),
            "created_utc": datetime.fromtimestamp(float(p.get("created_utc") or 0), tz=timezone.utc),
            "title": p.get("title"), "author": p.get("author"), "flair": p.get("link_flair_text"),
            "score": _int(p.get("score")), "num_comments": _int(p.get("num_comments")),
            "upvote_ratio": _float(p.get("upvote_ratio")), "url": p.get("url"),
            "permalink": ("https://www.reddit.com" + pl) if pl.startswith("/") else pl,
            "selftext": (p.get("selftext") or "")[:20000], "is_self": _bool(p.get("is_self")), "domain": p.get("domain"),
            "over_18": _bool(p.get("over_18")), "source": source,
        })
    df = pd.DataFrame(rows, columns=COLS)
    return df.drop_duplicates("id").sort_values("created_utc", ascending=False).reset_index(drop=True)


def _int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def _float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _bool(x):
    return str(x).lower() == "true" if x is not None else None


# --- Arctic Shift ---------------------------------------------------------------------------------------
def arctic(http: Http, flair: str | None = None, limit: int = 100, before: int | None = None, after: str | None = None) -> pd.DataFrame:
    params = {"subreddit": config.SUBREDDIT, "limit": limit, "sort": "desc"}
    if flair:
        params["link_flair_text"] = flair
    if before:
        params["before"] = before
    if after:
        params["after"] = after
    fx = "reddit/arctic_dd" if flair else "reddit/arctic_new"
    js = http.get_json(ARCTIC, params=params, headers={"User-Agent": config.REDDIT_USER_AGENT}, fixture=fx)
    return _normalize(js.get("data", []), "arctic_shift")


# --- Reddit OAuth (app-only) -----------------------------------------------------------------------------
def oauth_available() -> bool:
    return bool(config.REDDIT_CLIENT_ID and config.REDDIT_CLIENT_SECRET) and not config.fixture_mode()


def _token(http: Http) -> str:
    r = http.post("https://www.reddit.com/api/v1/access_token", data={"grant_type": "client_credentials"},
                  auth=(config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET), headers={"User-Agent": config.REDDIT_USER_AGENT})
    return r.json()["access_token"]


def reddit_oauth(http: Http, token: str, flair: str | None = None, limit: int = 100) -> pd.DataFrame:
    headers = {"Authorization": f"bearer {token}", "User-Agent": config.REDDIT_USER_AGENT}
    if flair:
        url = f"https://oauth.reddit.com/r/{config.SUBREDDIT}/search"
        params = {"q": f'flair_name:"{flair}"', "restrict_sr": 1, "sort": "new", "limit": limit, "t": "month", "raw_json": 1}
    else:
        url = f"https://oauth.reddit.com/r/{config.SUBREDDIT}/new"
        params = {"limit": limit, "raw_json": 1}
    js = http.get_json(url, params=params, headers=headers)
    posts = [c["data"] for c in (js.get("data") or {}).get("children", [])]
    return _normalize(posts, "reddit_oauth")


# --- the collector entry point ----------------------------------------------------------------------------
def fetch_latest(http: Http) -> pd.DataFrame:
    """Newest posts plus the newest Due Diligence posts, from Reddit if credentialed else Arctic Shift."""
    if oauth_available():
        try:
            tok = _token(http)
            new = reddit_oauth(http, tok)
            dd = reddit_oauth(http, tok, config.DD_FLAIR)
            return pd.concat([new, dd]).drop_duplicates("id").reset_index(drop=True)
        except Exception as e:
            log.warning("reddit oauth failed (%s); falling back to Arctic Shift", e)
    new = arctic(http)
    dd = arctic(http, config.DD_FLAIR)
    return pd.concat([new, dd]).drop_duplicates("id").reset_index(drop=True)


def backfill_dd(http: Http, days: int = 365, max_pages: int = 40) -> pd.DataFrame:
    """Walk back through Due Diligence posts with Arctic Shift's `before` cursor."""
    frames, before = [], None
    for _ in range(max_pages):
        df = arctic(http, config.DD_FLAIR, limit=100, before=before, after=f"{days}d")
        if df.empty:
            break
        frames.append(df)
        oldest = int(df["created_utc"].min().timestamp())
        if before is not None and oldest >= before:
            break
        before = oldest
        if len(df) < 100 or config.fixture_mode():
            break
    return pd.concat(frames).drop_duplicates("id").reset_index(drop=True) if frames else pd.DataFrame(columns=COLS)
