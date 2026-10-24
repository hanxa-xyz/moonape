"""FINRA Reg SHO daily short-sale volume (consolidated NMS file). Off-exchange (TRF/ADF) volume only; posted ~6pm ET."""
from __future__ import annotations

import io
import logging
from datetime import date, timedelta

import pandas as pd

from moonape.http import Http

log = logging.getLogger("moonape.finra")
URL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt"


def fetch_day(http: Http, d: date, symbols=("GME", "SPY")) -> pd.DataFrame:
    ymd = d.strftime("%Y%m%d")
    r = http.get(URL.format(ymd=ymd), fixture=f"finra/CNMSshvol{ymd}", ok_404=True)
    if getattr(r, "status_code", 200) == 404:
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(r.text), sep="|", dtype=str)
    df = df[df["Symbol"].isin(symbols)].copy()
    if df.empty:
        return df
    out = pd.DataFrame({
        "date": pd.to_datetime(df["Date"], format="%Y%m%d").dt.date, "symbol": df["Symbol"],
        "short_volume": pd.to_numeric(df["ShortVolume"], errors="coerce"),
        "short_exempt_volume": pd.to_numeric(df["ShortExemptVolume"], errors="coerce"),
        "total_volume": pd.to_numeric(df["TotalVolume"], errors="coerce"), "market": df["Market"],
    })
    out["short_share"] = out["short_volume"] / out["total_volume"]
    return out.reset_index(drop=True)


def fetch_recent(http: Http, end: date, days: int = 5) -> pd.DataFrame:
    frames = []
    for i in range(days):
        d = end - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        try:
            frames.append(fetch_day(http, d))
        except FileNotFoundError:
            pass
        except Exception as e:
            log.warning("finra %s failed: %s", d, e)
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
