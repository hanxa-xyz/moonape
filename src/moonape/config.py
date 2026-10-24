"""Paths, symbols, series, env. Everything configurable lives here."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(os.environ.get("MOONAPE_ROOT", Path(__file__).resolve().parents[2]))
load_dotenv(ROOT / ".env")

DATA = Path(os.environ.get("MOONAPE_DATA", ROOT / "data"))
SITE = ROOT / "site"
SITE_DATA = Path(os.environ.get("MOONAPE_SITE_DATA", SITE / "data"))
FIXTURES = ROOT / "tests" / "fixtures"


def fixture_mode() -> bool:
    return os.environ.get("MOONAPE_FIXTURE", "") not in ("", "0", "false", "no")


# --- what we track -------------------------------------------------------------------------------
UNDERLYING = "GME"
STOCKS = ["GME", "SPY"]

# SEC EDGAR: company and the two people whose filings move the stock
CIKS = {
    "0001326380": "GameStop Corp.",
    "0001767470": "Cohen Ryan",
    "0001871280": "Gill Keith",
}
GME_CUSIP = "36467W109"

# FRED series (daily unless noted). DEXJPUS is released weekly, so the yen tile uses Yahoo.
FRED_SERIES = {
    "DGS2": "2Y",
    "DGS5": "5Y",
    "DGS10": "10Y",
    "DGS30": "30Y",
    "T10Y2Y": "10Y-2Y",
    "DFF": "Fed funds (effective)",
    "DEXJPUS": "USD/JPY (H.10, weekly release)",
}

# Yahoo chart tickers for intraday macro. Values for ^IRX/^FVX/^TNX/^TYX are yields in percent.
YAHOO_TICKERS = {
    "^IRX": "13-week T-bill",
    "^FVX": "5Y",
    "^TNX": "10Y",
    "^TYX": "30Y",
    "JPY=X": "USD/JPY",
    "DX-Y.NYB": "DXY",
}

# Bank of Japan policy rate: no fresh machine-readable source; a dated constant (see README).
BOJ_POLICY_RATE = 1.25
BOJ_RATE_ASOF = "2026-09-24"

# --- credentials -----------------------------------------------------------------------------------
ALPACA_KEY = os.environ.get("APCA_API_KEY_ID", "")
ALPACA_SECRET = os.environ.get("APCA_API_SECRET_KEY", "")
ALPACA_TRADING_URL = os.environ.get("APCA_API_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
ALPACA_DATA_URL = os.environ.get("APCA_DATA_URL", "https://data.alpaca.markets").rstrip("/")
ALPACA_OPTION_FEED = os.environ.get("ALPACA_OPTION_FEED", "indicative")  # "opra" needs Algo Trader Plus
ALPACA_STOCK_FEED = os.environ.get("ALPACA_STOCK_FEED", "iex")  # "sip" needs Algo Trader Plus; "delayed_sip" is free

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "script:moonape:0.1 (by u/hanxa-xyz)")
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "moonape contact-not-set@example.com")

SUBREDDITS = ["Superstonk", "GME"]

# Socials: X accounts (read through twitterapi.io; needs TWITTERAPI_IO_KEY) and Truth Social (trumpstruth.org RSS mirror, keyless)
X_ACCOUNTS = {
    "ryancohen": "Ryan Cohen",
    "TheRoaringKitty": "Roaring Kitty",
    "larryvc": "Larry Cheng",
    "greg16676935420": "Greg",
    "elonmusk": "Elon Musk",
    "GameStop": "GameStop",
}
TRUTH_ACCOUNTS = {"realDonaldTrump": "Donald J. Trump"}
TWITTERAPI_IO_KEY = os.environ.get("TWITTERAPI_IO_KEY", "")
X_PAGES_PER_ACCOUNT = int(os.environ.get("X_PAGES_PER_ACCOUNT", "1"))  # 20 tweets per page; each returned tweet costs ~$0.00015

# Library: the public FlipHTML5 bookcase "SuperStonk Library of DD, Art Books, and Periodicals" (user zedinstead1)
LIBRARY_BOOKCASE_URL = "https://fliphtml5.com/bookcase/kosyg"
LIBRARY_ULINK = "lvrgy"
LIBRARY_BOOKCASE_FILE = ROOT / "library" / "bookcase.json"  # captured from the bookcase page (Cloudflare-walled for scripts)
LIBRARY_TEXT_PER_RUN = int(os.environ.get("LIBRARY_TEXT_PER_RUN", "25"))
LIBRARY_CURATED = [  # the "start here" shelf, matched on title substring, in this order
    "Diamond Handbook", "DD Mega Back Up", "House of Cards", "The Everything Short", "Citadel Has No Clothes", "The Bigger Short",
    "Dollar Endgame", "Naked Short Scam", "Infinity Pool", "Cellar Boxing", "Direct Registered Shares Thesis", "Computershare DD Series",
    "MOASS Thesis Summary", "Dictionary For The Non-Ape", "GMEdd.com November",
]
SUBREDDIT = SUBREDDITS[0]  # kept for backwards compatibility
DD_FLAIR = "Due Diligence"  # the live flair string is "📚 Due Diligence"; matched by substring
