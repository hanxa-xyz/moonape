"""OCC daily option volume for one underlying, by exchange, side (C/P) and account type (C customer, M market-maker, F firm)."""
from __future__ import annotations

import io
import logging
from datetime import date, timedelta

import pandas as pd

from moonape import config
from moonape.http import Http

log = logging.getLogger("moonape.occ")
URL = "https://marketdata.theocc.com/volume-query"


def fetch_day(http: Http, d: date, symbol: str = config.UNDERLYING) -> pd.DataFrame:
    ymd = d.strftime("%Y%m%d")
    params = {"reportDate": ymd, "format": "csv", "volumeQueryType": "O", "symbolType": "O", "symbol": symbol, "reportType": "D",
              "accountType": "ALL", "productKind": "OSTK", "porc": "BOTH"}
    r = http.get(URL, params=params, fixture=f"occ/{symbol}_{ymd}", ok_404=True)
    if getattr(r, "status_code", 200) == 404 or not r.text.strip():
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(r.text), dtype=str, index_col=False)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    if df.empty or "quantity" not in df.columns:
        return pd.DataFrame()
    out = pd.DataFrame({
        "date": pd.to_datetime(df["actdate"], format="%m/%d/%Y", errors="coerce").dt.date, "symbol": df["underlying"],
        "side": df["porc"].map({"C": "call", "P": "put"}), "account_type": df["actype"].map({"C": "customer", "M": "market_maker", "F": "firm"}),
        "exchange": df["exchange"], "quantity": pd.to_numeric(df["quantity"], errors="coerce"),
    })
    return out.dropna(subset=["date"]).reset_index(drop=True)


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
            log.warning("occ %s failed: %s", d, e)
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
