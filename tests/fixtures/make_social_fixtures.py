"""Synthetic twitterapi.io `last_tweets` response in the documented shape (the real service is paid; nothing is recorded)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "socials"
NOW = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)


def ts(dt):
    return dt.strftime("%a %b %d %H:%M:%S +0000 %Y")


def tweet(i, text, **kw):
    t = {"type": "tweet", "id": f"19800000000000{i:04d}", "url": f"https://x.com/fixtureuser/status/19800000000000{i:04d}", "text": text, "source": "",
         "retweetCount": 120 * i, "replyCount": 40 * i, "likeCount": 900 * i, "quoteCount": 10 * i, "viewCount": 50000 * i,
         "createdAt": ts(NOW - timedelta(hours=7 * i)), "lang": "en", "bookmarkCount": 5, "isReply": False, "inReplyToId": None,
         "conversationId": f"19800000000000{i:04d}", "displayTextRange": [0, len(text)], "inReplyToUserId": None, "inReplyToUsername": None,
         "author": {"type": "user", "userName": "fixtureuser", "url": "https://x.com/fixtureuser", "id": "1", "name": "Fixture User",
                    "isBlueVerified": True, "profilePicture": "", "followers": 1000000, "following": 10},
         "entities": {"hashtags": [], "urls": [], "user_mentions": []}, "quoted_tweet": None, "retweeted_tweet": None, "isLimitedReply": False}
    t.update(kw)
    return t


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    tweets = [
        tweet(1, "Hiring builders obsessed with SI. ta@gamestop.com"),
        tweet(2, "Power to the players.", quoted_tweet=tweet(9, "GameStop Q3 results are out.", url="https://x.com/GameStop/status/1980000000000009")),
        tweet(3, "RT @GameStop: Pre-orders live now.", retweeted_tweet=tweet(8, "Pre-orders live now.", url="https://x.com/GameStop/status/1980000000000008")),
        tweet(4, "Buy, hold, DRS."),
        tweet(5, "A reply to someone", isReply=True, inReplyToUsername="someone"),
    ]
    (OUT / "x_last_tweets.json").write_text(json.dumps({"status": "success", "code": 0, "msg": "success",
                                                        "data": {"pin_tweet": None, "tweets": tweets}, "has_next_page": False, "next_cursor": ""}, indent=1))
    print(f"wrote {len(tweets)} tweets → {OUT}")


if __name__ == "__main__":
    main()
