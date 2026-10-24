"""FRED observations (needs FRED_API_KEY). Daily series lag one business day; DEXJPUS is released weekly."""
from __future__ import annotations

import logging

import pandas as pd

from moonape import config
from moonape.http import Http

log = logging.getLogger("moonape.fred")
URL = "https://api.stlouisfed.org/fred/series/observations"


def available() -> bool:
    return bool(config.FRED_API_KEY) or config.fixture_mode()


def fetch_series(http: Http, series_id: str, start: str = "2010-01-01") -> pd.DataFrame:
    js = http.get_json(URL, params={"series_id": series_id, "api_key": config.FRED_API_KEY, "file_type": "json", "observation_start": start},
                       fixture="fred/observations")
    obs = js.get("observations", [])
    df = pd.DataFrame(obs)
    if df.empty:
        return df
    out = pd.DataFrame({"series_id": series_id, "label": config.FRED_SERIES.get(series_id, series_id),
                        "date": pd.to_datetime(df["date"]).dt.date, "value": pd.to_numeric(df["value"], errors="coerce")})
    return out.dropna(subset=["value"]).reset_index(drop=True)


def fetch_all(http: Http, start: str = "2010-01-01") -> pd.DataFrame:
    frames = []
    for sid in config.FRED_SERIES:
        try:
            frames.append(fetch_series(http, sid, start))
        except Exception as e:  # one bad series must not sink the rest
            log.warning("FRED %s failed: %s", sid, e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
