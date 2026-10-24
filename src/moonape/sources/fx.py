"""USD/JPY daily from Frankfurter (ECB reference rates, keyless, ~16:00 CET). The fallback when Yahoo rate-limits the runner."""
from __future__ import annotations

import pandas as pd

from moonape.http import Http

LATEST = "https://api.frankfurter.dev/v1/latest"
RANGE = "https://api.frankfurter.dev/v1/{start}.."


def usdjpy_latest(http: Http) -> pd.DataFrame:
    js = http.get_json(LATEST, params={"base": "USD", "symbols": "JPY"}, fixture="fx/frankfurter_latest")
    return _rows({js["date"]: js["rates"]})


def usdjpy_history(http: Http, start: str) -> pd.DataFrame:
    js = http.get_json(RANGE.format(start=start), params={"base": "USD", "symbols": "JPY"}, fixture="fx/frankfurter_hist")
    return _rows(js.get("rates", {}))


def _rows(rates: dict) -> pd.DataFrame:
    rows = [{"ticker": "JPY=X", "label": "USD/JPY", "ts": pd.Timestamp(d, tz="UTC") + pd.Timedelta(hours=15), "open": None, "high": None, "low": None,
             "close": float(v["JPY"]), "volume": None, "interval": "1d", "regular_market_price": float(v["JPY"]), "source": "frankfurter"}
            for d, v in sorted(rates.items()) if v.get("JPY") is not None]
    return pd.DataFrame(rows)
