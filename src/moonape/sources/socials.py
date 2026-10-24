"""Social posts: X via twitterapi.io (paid reseller, ~$0.15 per 1k tweets; needs TWITTERAPI_IO_KEY) and Truth Social via the
trumpstruth.org RSS mirror (keyless). One schema for both platforms.

X has no free read path in 2026: syndication endpoints are dead, Nitter is gone, the official API is pay-per-use only.
"""
from __future__ import annotations

import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import pandas as pd

from moonape import config
from moonape.http import Http

log = logging.getLogger("moonape.socials")
X_URL = "https://api.twitterapi.io/twitter/user/last_tweets"
TRUTH_FEED = "https://www.trumpstruth.org/feed"
NS = {"truth": "https://truthsocial.com/ns", "archive": "https://www.trumpstruth.org/rss-extensions",
      "media": "http://search.yahoo.com/mrss/", "dc": "http://purl.org/dc/elements/1.1/"}
COLS = ["platform", "account", "account_name", "post_id", "created_at", "text", "url", "likes", "reposts", "replies", "quotes", "views",
        "is_reply", "is_repost", "is_quote", "quoted_text", "quoted_url", "media_url", "lang", "source"]
_TAGS = re.compile(r"<[^>]+>")


def _strip(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p>\s*<p>", "\n\n", s, flags=re.I)
    return html.unescape(_TAGS.sub("", s)).strip()


# --- X via twitterapi.io ---------------------------------------------------------------------------------
def x_available() -> bool:
    return bool(config.TWITTERAPI_IO_KEY) or config.fixture_mode()


def _x_time(s: str | None):
    if not s:
        return pd.NaT
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y").astimezone(timezone.utc)
    except ValueError:
        return pd.to_datetime(s, utc=True, errors="coerce")


def x_last_tweets(http: Http, username: str, pages: int = 1, include_replies: bool = False) -> pd.DataFrame:
    rows, cursor = [], ""
    for _ in range(max(1, pages)):
        params = {"userName": username, "cursor": cursor, "includeReplies": str(include_replies).lower()}
        js = http.get_json(X_URL, params=params, headers={"X-API-Key": config.TWITTERAPI_IO_KEY}, fixture="socials/x_last_tweets")
        if js.get("status") == "error":
            raise RuntimeError(f"twitterapi.io: {js.get('msg') or js.get('message')}")
        data = js.get("data") or {}
        for t in data.get("tweets") or []:
            rows.append(_x_row(t, username))
        if not js.get("has_next_page") or not js.get("next_cursor"):
            break
        cursor = js["next_cursor"]
    return pd.DataFrame(rows, columns=COLS)


def _x_row(t: dict, username: str) -> dict:
    author = t.get("author") or {}
    rt, qt = t.get("retweeted_tweet"), t.get("quoted_tweet")
    media = None
    for key in ("extendedEntities", "entities"):
        for m in ((t.get(key) or {}).get("media") or []):
            media = m.get("media_url_https") or m.get("media_url") or m.get("url")
            if media:
                break
        if media:
            break
    return {
        "platform": "x", "account": username.lower(), "account_name": config.X_ACCOUNTS.get(username) or author.get("name") or username,
        "post_id": str(t.get("id")), "created_at": _x_time(t.get("createdAt")), "text": t.get("text") or "",
        "url": t.get("url") or f"https://x.com/{username}/status/{t.get('id')}",
        "likes": t.get("likeCount"), "reposts": t.get("retweetCount"), "replies": t.get("replyCount"), "quotes": t.get("quoteCount"),
        "views": t.get("viewCount"), "is_reply": bool(t.get("isReply")), "is_repost": rt is not None, "is_quote": qt is not None,
        "quoted_text": (qt or rt or {}).get("text") if (qt or rt) else None, "quoted_url": (qt or rt or {}).get("url") if (qt or rt) else None,
        "media_url": media, "lang": t.get("lang"), "source": "twitterapi.io",
    }


def _split_truth(desc_html: str, kind: str | None) -> tuple[str, str | None]:
    """The mirror renders a quote as `<main>…</p><p>Quoted <a>Name</a>…` and a repost as `RT @handle…` + `<p>Reposted <a>Name</a>…`
    (the reposted body twice). Return (own text, quoted text or None)."""
    m = re.search(r"<p>\s*(Quoted|Reposted)\s+<a[^>]*>.*?</a>", desc_html, flags=re.S)
    main_html, tail_html = (desc_html[:m.start()], desc_html[m.end():]) if m else (desc_html, "")
    text = _strip(main_html)
    text = re.sub(r"^\s*RT:\s*https?://\S*?/statuses/\d+\s*", "", text)  # "RT: <original url>" prefix on quotes (no space follows)
    handles = "|".join(re.escape(h) for h in config.TRUTH_ACCOUNTS)
    text = re.sub(rf"^\s*RT\s+@(?:{handles})\s*", "", text)  # "RT @handle" prefix on reposts (no space follows either)
    quoted = _strip(tail_html) or None
    if kind == "repost" and quoted and quoted[:80] == text[:80]:
        quoted = None  # the mirror repeats the reposted body; keep one copy
    return text, quoted


# --- Truth Social via trumpstruth.org ------------------------------------------------------------------------
def truth_feed(http: Http, limit: int = 100, start_date: str | None = None) -> pd.DataFrame:
    params = {"limit": limit}
    if start_date:
        params["start_date"] = start_date
    r = http.get(TRUTH_FEED, params=params, fixture="socials/trumpstruth")
    root = ET.fromstring(r.content)
    rows = []
    for it in root.iter("item"):
        desc = it.findtext("description") or ""
        post_type = it.findtext("archive:postType", namespaces=NS) or "original"
        ref = it.find("archive:reference", NS)
        ref_type = ref.get("type") if ref is not None else None
        text, quoted = _split_truth(desc, post_type if post_type != "original" else ref_type)
        media = it.find("media:content", NS)
        rows.append({
            "platform": "truth", "account": "realDonaldTrump", "account_name": config.TRUTH_ACCOUNTS["realDonaldTrump"],
            "post_id": it.findtext("truth:originalId", namespaces=NS) or it.findtext("guid"),
            "created_at": parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc) if it.findtext("pubDate") else pd.NaT,
            "text": text or (it.findtext("title") or ""),
            "url": it.findtext("truth:originalUrl", namespaces=NS) or it.findtext("link"),
            "likes": None, "reposts": None, "replies": None, "quotes": None, "views": None,
            "is_reply": False, "is_repost": post_type == "repost" or ref_type == "repost", "is_quote": post_type == "quote" or ref_type == "quote",
            "quoted_text": quoted, "quoted_url": (f"https://truthsocial.com/@realDonaldTrump/{ref.get('originalId')}" if ref is not None and ref.get("originalId") else None),
            "media_url": media.get("url") if media is not None else None, "lang": "en", "source": "trumpstruth.org",
        })
    df = pd.DataFrame(rows, columns=COLS)
    removed = {it.findtext("truth:originalId", namespaces=NS) for it in root.iter("item") if (it.findtext("archive:removed", namespaces=NS) or "").lower() == "true"}
    df["removed"] = df["post_id"].isin(removed)
    return df


# --- collector entry points ----------------------------------------------------------------------------------
def fetch_x(http: Http) -> pd.DataFrame:
    frames, errors = [], []
    for user in config.X_ACCOUNTS:
        try:
            frames.append(x_last_tweets(http, user, pages=config.X_PAGES_PER_ACCOUNT))
        except Exception as e:
            errors.append(f"{user}: {e}")
            log.warning("x %s failed: %s", user, e)
    if not frames and errors:
        raise RuntimeError("every X account failed: " + "; ".join(errors))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLS)


def fetch_truth(http: Http) -> pd.DataFrame:
    return truth_feed(http, limit=100)
