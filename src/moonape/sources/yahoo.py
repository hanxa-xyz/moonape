"""Yahoo Finance chart JSON for intraday yields (^IRX ^FVX ^TNX ^TYX), USD/JPY (JPY=X) and DXY. Best effort; throttled."""
from __future__ import annotations

import logging

import pandas as pd

from moonape import config
from moonape.http import Http

log = logging.getLogger("moonape.yahoo")
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "application/json"}


def _slug(ticker: str) -> str:
    return ticker.replace("^", "").replace("=", "_").replace(".", "_").replace("-", "_")


def fetch(http: Http, ticker: str, range_: str = "1d", interval: str = "5m") -> pd.DataFrame:
    js = http.get_json(URL.format(ticker=ticker), params={"range": range_, "interval": interval, "includePrePost": "false"},
                       headers=HEADERS, fixture=f"yahoo/{_slug(ticker)}")
    res = (js.get("chart") or {}).get("result") or []
    if not res:
        return pd.DataFrame()
    r = res[0]
    q = (r.get("indicators") or {}).get("quote", [{}])[0]
    ts = r.get("timestamp") or []
    df = pd.DataFrame({"ts": pd.to_datetime(ts, unit="s", utc=True), "open": q.get("open"), "high": q.get("high"), "low": q.get("low"),
                       "close": q.get("close"), "volume": q.get("volume")})
    df = df.dropna(subset=["close"])
    df.insert(0, "ticker", ticker)
    df.insert(1, "label", config.YAHOO_TICKERS.get(ticker, ticker))
    df["interval"] = interval
    meta = r.get("meta") or {}
    df["regular_market_price"] = meta.get("regularMarketPrice")
    return df.reset_index(drop=True)


def fetch_all(http: Http, range_: str = "1d", interval: str = "5m") -> pd.DataFrame:
    frames = []
    for t in config.YAHOO_TICKERS:
        try:
            frames.append(fetch(http, t, range_, interval))
        except FileNotFoundError:
            log.info("yahoo %s: no fixture, skipped", t)
        except Exception as e:
            log.warning("yahoo %s failed: %s", t, e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
