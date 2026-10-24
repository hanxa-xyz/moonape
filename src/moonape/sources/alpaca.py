"""Alpaca Market Data + Trading API, plain REST.

Endpoints used (free Basic plan unless noted):
  GET {trading}/v2/clock                                   market open flag, next open/close
  GET {trading}/v2/calendar?start&end                      session open/close times per day
  GET {trading}/v2/options/contracts?underlying_symbols=   contract list incl. prior-day open_interest  (limit ≤ 10000)
  GET {data}/v2/stocks/snapshots?symbols=&feed=iex         latest trade/quote/minute/day/prev-day bars
  GET {data}/v2/stocks/bars?symbols=&timeframe=&start=     history since 2016 (feed=sip needs end ≥ 15 min old)
  GET {data}/v1beta1/options/snapshots/{underlying}?feed=  whole chain: quote, trade, greeks, impliedVolatility, dailyBar (limit ≤ 1000/page)
  GET {data}/v1beta1/options/bars?symbols=&timeframe=      option bar history since 2024-02 (backfill)
alpaca-py equivalents: TradingClient.get_clock / get_calendar / get_option_contracts,
StockHistoricalDataClient.get_stock_snapshot / get_stock_bars, OptionHistoricalDataClient.get_option_chain / get_option_bars.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from moonape import config
from moonape.http import Http

log = logging.getLogger("moonape.alpaca")

OCC_RE = re.compile(r"^(?P<root>[A-Z]{1,6})(?P<ymd>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")


class MissingCredentials(RuntimeError):
    pass


def _headers() -> dict:
    if not config.ALPACA_KEY or not config.ALPACA_SECRET:
        if config.fixture_mode():
            return {}
        raise MissingCredentials("APCA_API_KEY_ID / APCA_API_SECRET_KEY are not set (see .env.example)")
    return {"APCA-API-KEY-ID": config.ALPACA_KEY, "APCA-API-SECRET-KEY": config.ALPACA_SECRET, "Accept": "application/json"}


def parse_occ(symbol: str) -> dict:
    """GME251121C00025000 → root GME, expiration 2025-11-21, type call, strike 25.0"""
    m = OCC_RE.match(symbol)
    if not m:
        raise ValueError(f"not an OCC option symbol: {symbol}")
    ymd = m["ymd"]
    return {
        "root": m["root"],
        "expiration": date(2000 + int(ymd[:2]), int(ymd[2:4]), int(ymd[4:6])),
        "type": "call" if m["cp"] == "C" else "put",
        "strike": int(m["strike"]) / 1000.0,
    }


def _ts(x):
    return pd.to_datetime(x, utc=True) if x else pd.NaT


# --- Trading API -------------------------------------------------------------------------------------
def clock(http: Http) -> dict:
    return http.get_json(f"{config.ALPACA_TRADING_URL}/v2/clock", headers=_headers(), fixture="alpaca/clock")


def calendar(http: Http, start: date, end: date) -> list[dict]:
    return http.get_json(f"{config.ALPACA_TRADING_URL}/v2/calendar", headers=_headers(),
                         params={"start": start.isoformat(), "end": end.isoformat()}, fixture="alpaca/calendar")


def in_collection_window(http: Http, now: datetime, before_open_min: int = 5, after_close_min: int = 35) -> tuple[bool, str]:
    """True from shortly before the open to shortly after the close on a trading day (the post-close run captures the settle)."""
    ny = now.astimezone(_ny())
    days = calendar(http, ny.date(), ny.date())
    if not days or days[0].get("date") != ny.date().isoformat():
        return False, f"{ny.date()} is not a trading day"
    d = days[0]
    open_t = datetime.combine(ny.date(), datetime.strptime(d["open"], "%H:%M").time(), tzinfo=_ny())
    close_t = datetime.combine(ny.date(), datetime.strptime(d["close"], "%H:%M").time(), tzinfo=_ny())
    lo, hi = open_t - timedelta(minutes=before_open_min), close_t + timedelta(minutes=after_close_min)
    if lo <= ny <= hi:
        return True, f"inside window {lo:%H:%M}–{hi:%H:%M} ET"
    return False, f"{ny:%H:%M} ET is outside {lo:%H:%M}–{hi:%H:%M} ET"


def _ny():
    from zoneinfo import ZoneInfo
    return ZoneInfo("America/New_York")


def option_contracts(http: Http, underlying: str = config.UNDERLYING, exp_gte: date | None = None, exp_lte: date | None = None,
                     asof: date | None = None) -> pd.DataFrame:
    """Every active contract with its prior-day open interest. The expiry window must be explicit or Alpaca returns only this week."""
    asof = asof or date.today()
    params = {
        "underlying_symbols": underlying,
        "status": "active",
        "limit": 10000,
        "expiration_date_gte": (exp_gte or asof).isoformat(),
        "expiration_date_lte": (exp_lte or asof + timedelta(days=3 * 366)).isoformat(),
    }
    rows, token = [], None
    while True:
        if token:
            params["page_token"] = token
        js = http.get_json(f"{config.ALPACA_TRADING_URL}/v2/options/contracts", headers=_headers(), params=params,
                           fixture="alpaca/option_contracts")
        rows.extend(js.get("option_contracts", []))
        token = js.get("next_page_token")
        if not token:
            break
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "symbol": df["symbol"],
        "underlying": df["underlying_symbol"],
        "expiration": pd.to_datetime(df["expiration_date"]).dt.date,
        "strike": pd.to_numeric(df["strike_price"]),
        "type": df["type"],
        "style": df.get("style"),
        "open_interest": pd.to_numeric(df.get("open_interest"), errors="coerce"),
        "open_interest_date": pd.to_datetime(df.get("open_interest_date"), errors="coerce").dt.date,
        "close_price": pd.to_numeric(df.get("close_price"), errors="coerce"),
        "close_price_date": pd.to_datetime(df.get("close_price_date"), errors="coerce").dt.date,
        "multiplier": pd.to_numeric(df.get("multiplier"), errors="coerce"),
        "tradable": df.get("tradable"),
        "status": df.get("status"),
    })
    return out


# --- Market Data: stocks ---------------------------------------------------------------------------------
def stock_snapshots(http: Http, symbols=config.STOCKS, feed: str = config.ALPACA_STOCK_FEED) -> pd.DataFrame:
    js = http.get_json(f"{config.ALPACA_DATA_URL}/v2/stocks/snapshots", headers=_headers(),
                       params={"symbols": ",".join(symbols), "feed": feed}, fixture="alpaca/stock_snapshots")
    rows = []
    for sym, s in js.items():
        lt, lq = s.get("latestTrade") or {}, s.get("latestQuote") or {}
        mb, db, pb = s.get("minuteBar") or {}, s.get("dailyBar") or {}, s.get("prevDailyBar") or {}
        rows.append({
            "symbol": sym, "feed": feed,
            "ts": _ts(lt.get("t")), "price": lt.get("p"), "size": lt.get("s"), "exchange": lt.get("x"),
            "quote_ts": _ts(lq.get("t")), "bid": lq.get("bp"), "bid_size": lq.get("bs"), "ask": lq.get("ap"), "ask_size": lq.get("as"),
            "minute_ts": _ts(mb.get("t")), "minute_open": mb.get("o"), "minute_high": mb.get("h"), "minute_low": mb.get("l"),
            "minute_close": mb.get("c"), "minute_volume": mb.get("v"),
            "day_open": db.get("o"), "day_high": db.get("h"), "day_low": db.get("l"), "day_close": db.get("c"),
            "day_volume": db.get("v"), "day_vwap": db.get("vw"), "day_trades": db.get("n"),
            "prev_close": pb.get("c"), "prev_volume": pb.get("v"), "prev_date": _ts(pb.get("t")),
        })
    return pd.DataFrame(rows)


def stock_bars(http: Http, symbols, timeframe: str, start: datetime, end: datetime | None = None, feed: str = "sip",
               adjustment: str = "all", limit: int = 10000) -> pd.DataFrame:
    """Historical bars. On Basic, SIP history is allowed when `end` is ≥ 15 minutes old, so end defaults to now-16min."""
    end = end or (datetime.now(timezone.utc) - timedelta(minutes=16))
    params = {"symbols": ",".join(symbols), "timeframe": timeframe, "start": start.isoformat(), "end": end.isoformat(),
              "limit": limit, "adjustment": adjustment, "feed": feed, "sort": "asc"}
    rows, token = [], None
    while True:
        if token:
            params["page_token"] = token
        js = http.get_json(f"{config.ALPACA_DATA_URL}/v2/stocks/bars", headers=_headers(), params=params,
                           fixture=f"alpaca/stock_bars_{timeframe}")
        for sym, bars in (js.get("bars") or {}).items():
            for b in bars or []:
                rows.append({"symbol": sym, "timeframe": timeframe, "t": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
                             "close": b["c"], "volume": b["v"], "trades": b.get("n"), "vwap": b.get("vw")})
        token = js.get("next_page_token")
        if not token:
            break
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df


# --- Market Data: options -------------------------------------------------------------------------------
def option_chain(http: Http, underlying: str = config.UNDERLYING, feed: str = config.ALPACA_OPTION_FEED) -> pd.DataFrame:
    """The whole chain in one or a few pages: quote, trade, greeks, IV, day bar. No open interest here (see option_contracts)."""
    params = {"feed": feed, "limit": 1000}
    snaps, token = {}, None
    while True:
        if token:
            params["page_token"] = token
        js = http.get_json(f"{config.ALPACA_DATA_URL}/v1beta1/options/snapshots/{underlying}", headers=_headers(), params=params,
                           fixture="alpaca/option_chain")
        snaps.update(js.get("snapshots") or {})
        token = js.get("next_page_token")
        if not token:
            break
    rows = []
    for sym, s in snaps.items():
        try:
            occ = parse_occ(sym)
        except ValueError:
            continue
        q, t, g = s.get("latestQuote") or {}, s.get("latestTrade") or {}, s.get("greeks") or {}
        db, pb = s.get("dailyBar") or {}, s.get("prevDailyBar") or {}
        rows.append({
            "symbol": sym, "underlying": underlying, "feed": feed,
            "expiration": occ["expiration"], "strike": occ["strike"], "type": occ["type"],
            "bid": q.get("bp"), "bid_size": q.get("bs"), "ask": q.get("ap"), "ask_size": q.get("as"), "quote_ts": _ts(q.get("t")),
            "last": t.get("p"), "last_size": t.get("s"), "last_ts": _ts(t.get("t")),
            "day_open": db.get("o"), "day_high": db.get("h"), "day_low": db.get("l"), "day_close": db.get("c"),
            "day_volume": db.get("v"), "day_vwap": db.get("vw"), "day_trades": db.get("n"), "prev_close": pb.get("c"),
            "iv": s.get("impliedVolatility"),
            "delta": g.get("delta"), "gamma": g.get("gamma"), "theta": g.get("theta"), "vega": g.get("vega"), "rho": g.get("rho"),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for c in ("bid", "ask", "last", "day_volume", "iv", "delta", "gamma", "theta", "vega", "rho"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["day_volume"] = df["day_volume"].fillna(0).astype("int64")
    return df.sort_values(["expiration", "strike", "type"]).reset_index(drop=True)


def option_bars(http: Http, symbols: list[str], timeframe: str, start: datetime, end: datetime | None = None,
                limit: int = 10000) -> pd.DataFrame:
    """Option bar history (since 2024-02), ≤ 100 symbols per call. Used by the IV-history backfill (follow-up)."""
    rows = []
    for i in range(0, len(symbols), 100):
        params = {"symbols": ",".join(symbols[i:i + 100]), "timeframe": timeframe, "start": start.isoformat(), "limit": limit, "sort": "asc"}
        if end:
            params["end"] = end.isoformat()
        token = None
        while True:
            if token:
                params["page_token"] = token
            js = http.get_json(f"{config.ALPACA_DATA_URL}/v1beta1/options/bars", headers=_headers(), params=params, fixture="alpaca/option_bars")
            for sym, bars in (js.get("bars") or {}).items():
                for b in bars or []:
                    rows.append({"symbol": sym, "timeframe": timeframe, "t": b["t"], "open": b["o"], "high": b["h"], "low": b["l"],
                                 "close": b["c"], "volume": b["v"], "trades": b.get("n"), "vwap": b.get("vw")})
            token = js.get("next_page_token")
            if not token:
                break
    df = pd.DataFrame(rows)
    if not df.empty:
        df["t"] = pd.to_datetime(df["t"], utc=True)
    return df
