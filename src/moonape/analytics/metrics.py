"""One row of headline chain metrics per snapshot (persisted as `chain_metrics`, the history the dashboard charts)."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from moonape.analytics import gex as gexmod
from moonape.analytics import iv as ivmod
from moonape.analytics import maxpain


def chain_metrics(chain: pd.DataFrame, spot: float, asof: datetime) -> pd.DataFrame:
    if chain.empty:
        return pd.DataFrame()
    mp = maxpain.max_pain_table(chain)
    term = ivmod.term_structure(chain)
    skew = ivmod.skew_25d(chain)
    g = gexmod.gex_by_strike(chain)
    live = mp[mp["dte"] > 0]
    front = live.iloc[0] if not live.empty else (mp.iloc[0] if not mp.empty else None)
    monthly = _next_monthly(live)
    row = {
        "ts": pd.Timestamp(asof).tz_convert("UTC") if pd.Timestamp(asof).tzinfo else pd.Timestamp(asof, tz="UTC"),
        "spot": float(spot),
        "front_expiry": front["expiration"] if front is not None else None,
        "front_dte": int(front["dte"]) if front is not None else None,
        "front_max_pain": float(front["max_pain"]) if front is not None else np.nan,
        "front_call_wall": float(front["call_wall"]) if front is not None else np.nan,
        "front_put_wall": float(front["put_wall"]) if front is not None else np.nan,
        "monthly_expiry": monthly["expiration"] if monthly is not None else None,
        "monthly_max_pain": float(monthly["max_pain"]) if monthly is not None else np.nan,
        "call_oi": int(mp["call_oi"].sum()), "put_oi": int(mp["put_oi"].sum()),
        "pc_oi": float(mp["put_oi"].sum() / mp["call_oi"].sum()) if mp["call_oi"].sum() else np.nan,
        "call_vol": int(mp["call_vol"].sum()), "put_vol": int(mp["put_vol"].sum()),
        "pc_vol": float(mp["put_vol"].sum() / mp["call_vol"].sum()) if mp["call_vol"].sum() else np.nan,
        "iv30": ivmod.interpolate_iv(term, 30), "iv60": ivmod.interpolate_iv(term, 60),
        "atm_iv_front": float(term["atm_iv"].iloc[0]) if not term.empty else np.nan,
        "skew25_front": float(skew["skew25"].iloc[0]) if not skew.empty else np.nan,
        "net_gex": gexmod.total_gex(g), "zero_gamma": gexmod.zero_gamma(g),
        "n_contracts": int(len(chain)), "n_with_iv": int(chain["iv"].notna().sum()),
        "n_with_oi": int(chain["open_interest"].notna().sum()),
        "oi_date": chain["open_interest_date"].dropna().max() if chain["open_interest_date"].notna().any() else None,
    }
    return pd.DataFrame([row])


def _next_monthly(mp: pd.DataFrame):
    """Standard monthly = third Friday. Returns the first such row with dte > 0."""
    for _, r in mp.iterrows():
        e = pd.Timestamp(r["expiration"])
        if e.weekday() == 4 and 15 <= e.day <= 21:
            return r
    return None
