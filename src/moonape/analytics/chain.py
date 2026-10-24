"""Join a chain snapshot with the latest contracts (open interest) into one tidy row per contract."""
from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd

CHAIN_COLS = ["snapshot_ts", "symbol", "underlying", "expiration", "dte", "strike", "type", "moneyness", "spot",
              "bid", "ask", "mid", "last", "day_volume", "iv", "delta", "gamma", "theta", "vega", "rho",
              "open_interest", "open_interest_date", "feed"]


def tidy_chain(chain: pd.DataFrame, contracts: pd.DataFrame | None, spot: float, asof: datetime) -> pd.DataFrame:
    """chain = alpaca.option_chain(); contracts = alpaca.option_contracts() (may be empty → OI NaN)."""
    if chain is None or chain.empty:
        return pd.DataFrame(columns=CHAIN_COLS)
    df = chain.copy()
    if contracts is not None and not contracts.empty:
        oi = contracts[["symbol", "open_interest", "open_interest_date"]].drop_duplicates("symbol")
        df = df.merge(oi, on="symbol", how="left")
    else:
        df["open_interest"] = np.nan
        df["open_interest_date"] = pd.NaT
    asof_date: date = asof.date() if isinstance(asof, datetime) else asof
    df["expiration"] = pd.to_datetime(df["expiration"]).dt.date
    df["dte"] = [(e - asof_date).days for e in df["expiration"]]
    df["spot"] = float(spot)
    df["moneyness"] = df["strike"] / float(spot)
    df["mid"] = np.where(df["bid"].notna() & df["ask"].notna() & (df["ask"] > 0), (df["bid"].fillna(0) + df["ask"]) / 2, np.nan)
    df["snapshot_ts"] = pd.Timestamp(asof).tz_convert("UTC") if pd.Timestamp(asof).tzinfo else pd.Timestamp(asof, tz="UTC")
    df["open_interest"] = pd.to_numeric(df["open_interest"], errors="coerce")
    df = df[df["dte"] >= 0]
    return df[CHAIN_COLS].sort_values(["expiration", "strike", "type"]).reset_index(drop=True)
