from datetime import date, datetime, timezone

from moonape.sources import alpaca, edgar, finra, fred, occ, reddit, treasury, yahoo


def test_alpaca_clock_and_window(http):
    c = alpaca.clock(http)
    assert c["is_open"] is True
    ok, why = alpaca.in_collection_window(http, datetime(2026, 10, 23, 15, 30, tzinfo=timezone.utc))
    assert ok, why
    ok, _ = alpaca.in_collection_window(http, datetime(2026, 10, 23, 23, 0, tzinfo=timezone.utc))
    assert not ok


def test_alpaca_stock_snapshots(http):
    df = alpaca.stock_snapshots(http)
    assert set(df["symbol"]) == {"GME", "SPY"}
    assert df.set_index("symbol").loc["GME", "price"] == 24.6


def test_alpaca_bars(http):
    d = alpaca.stock_bars(http, ["GME", "SPY"], "1Day", datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert len(d) == 600 and d["t"].dt.tz is not None
    i = alpaca.stock_bars(http, ["GME", "SPY"], "15Min", datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert len(i) == 208


def test_treasury_long_table(http):
    t = treasury.fetch_year(http, 2026)
    assert {"date", "tenor", "months", "yield"} <= set(t.columns)
    last = t[t["date"] == t["date"].max()].set_index("tenor")["yield"]
    assert last["10Y"] == 5.00 and last["2Y"] == 4.69 and last["30Y"] == 5.33


def test_fred_observations(http):
    f = fred.fetch_series(http, "DGS10")
    assert f["value"].notna().all() and len(f) > 150 and f["label"].iloc[0] == "10Y"


def test_yahoo_chart(http):
    t = yahoo.fetch(http, "^TNX")
    assert len(t) == 80 and t["label"].iloc[0] == "10Y" and abs(t["close"].iloc[-1] - 4.99) < 0.05
    j = yahoo.fetch(http, "JPY=X")
    assert 100 < j["close"].iloc[-1] < 250
    allf = yahoo.fetch_all(http)  # tickers without a fixture are skipped, not fatal
    assert set(allf["ticker"]) == {"^TNX", "JPY=X"}


def test_reddit_arctic(http):
    df = reddit.fetch_latest(http)
    assert len(df) > 25 and df["id"].is_unique
    assert df["flair"].str.contains("Due Diligence").sum() >= 25
    assert df["created_utc"].dt.tz is not None and df["score"].dtype.kind in "if"
    assert df["permalink"].str.startswith("https://www.reddit.com/").all()
    assert set(df["subreddit"]) == {"Superstonk", "GME"}


def test_edgar_submissions(http):
    gme = edgar.submissions(http, "0001326380")
    assert gme["entity"].iloc[0].startswith("GameStop") and len(gme) > 900
    assert gme["form"].iloc[0] == "8-K" and gme["url"].iloc[0].startswith("https://www.sec.gov/Archives/edgar/data/1326380/")
    cohen = edgar.submissions(http, "0001767470")
    assert cohen["form"].str.contains("13D").any()
    everyone = edgar.all_submissions(http)
    assert set(everyone["cik"]) == {"0001326380", "0001767470", "0001871280"}


def test_edgar_13f(http):
    h = edgar.holders_13f(http, date(2026, 4, 1), date(2026, 10, 24))
    assert len(h) >= 50 and h["adsh"].is_unique and h["form"].str.startswith("13F-HR").all()


def test_finra(http):
    f = finra.fetch_day(http, date(2026, 10, 23))
    gme = f[f["symbol"] == "GME"].iloc[0]
    assert 0.5 < gme["short_share"] < 0.9 and gme["total_volume"] > 4_000_000
    assert len(finra.fetch_recent(http, date(2026, 10, 23))) == 2


def test_occ(http):
    o = occ.fetch_day(http, date(2026, 10, 23))
    assert set(o["side"]) == {"call", "put"} and o["quantity"].sum() > 300_000
    assert o["exchange"].nunique() > 10
