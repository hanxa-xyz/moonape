from datetime import timezone

from moonape.sources import library, socials


def test_x_last_tweets_fixture(http):
    df = socials.x_last_tweets(http, "ryancohen")
    assert len(df) == 5 and df["platform"].eq("x").all() and df["account"].eq("ryancohen").all()
    assert df["account_name"].iloc[0] == "Ryan Cohen"
    assert df["created_at"].dt.tz is not None and df["created_at"].is_monotonic_decreasing
    assert df["is_quote"].sum() == 1 and df["is_repost"].sum() == 1 and df["is_reply"].sum() == 1
    assert df.loc[df["is_quote"], "quoted_text"].iloc[0] == "GameStop Q3 results are out."


def test_fetch_x_covers_every_configured_account(http):
    df = socials.fetch_x(http)
    assert set(df["account"]) == {a.lower() for a in socials.config.X_ACCOUNTS}


def test_truth_feed_fixture(http):
    df = socials.truth_feed(http)
    assert len(df) == 30 and df["platform"].eq("truth").all()
    assert df["post_id"].str.isdigit().all() and df["url"].str.startswith("https://truthsocial.com/@realDonaldTrump/").all()
    assert df["created_at"].iloc[0].tzinfo == timezone.utc
    assert df["is_quote"].sum() >= 5 and df["is_repost"].sum() >= 1
    assert not df["text"].str.startswith("RT").any() and df["text"].str.len().min() > 0
    assert not df["text"].str.contains("Quoted Donald|Reposted Donald").any()
    q = df[df["is_quote"]].iloc[0]
    assert q["quoted_text"] and not q["quoted_text"].startswith("Quoted") and q["quoted_text"][:40] not in q["text"]
    assert df["media_url"].notna().sum() >= 1


def test_bookcase_catalog():
    cat = library.load_bookcase()
    assert len(cat) == 250 and cat["blink"].is_unique and cat["pages"].sum() == 6821
    assert cat.loc[cat["blink"] == "ezim", "title"].iloc[0] == "Diamond Handbook"
    assert cat["curated_rank"].notna().sum() >= 10 and cat["url"].str.startswith("https://online.fliphtml5.com/lvrgy/").all()
    assert cat.sort_values("curated_rank").dropna(subset=["curated_rank"])["title"].iloc[0] == "Diamond Handbook"


def test_book_text_layer(http):
    pages = library.fetch_text(http, "jpfu")
    assert len(pages) == 8 and pages[0] == "" and "GMEdd.com" in pages[2]
    stats, text = library.fetch_books_text(http, ["jpfu", "nope"])  # missing fixture is skipped, not fatal
    assert len(stats) == 1 and stats["text_pages"].iloc[0] >= 4 and stats["excerpt"].iloc[0].startswith("GMEdd.com")
    assert (text["blink"] == "jpfu").all() and text["page"].min() == 3


def test_text_cleaner_drops_lone_surrogates():
    assert library._clean("GME \ud83d to the  moon") == "GME to the moon"
    "x".join(library._clean("ok \ud83d\ude80")).encode("utf-8")  # must be encodable
