"""Implied-volatility views: term structure, 25-delta skew, IV30, IV rank/percentile, surface."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

MONEYNESS_EDGES = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0, 1.05, 1.1, 1.2, 1.3, 1.5, 1.75, 2.0, 2.5]


def _with_iv(chain: pd.DataFrame) -> pd.DataFrame:
    return chain[chain["iv"].notna() & (chain["iv"] > 0) & (chain["dte"] > 0)]


def term_structure(chain: pd.DataFrame) -> pd.DataFrame:
    """ATM IV per expiration: the strike nearest spot, call and put IV averaged when both exist."""
    rows = []
    for exp, g in _with_iv(chain).groupby("expiration", sort=True):
        spot = float(g["spot"].iloc[0])
        k = g.loc[(g["strike"] - spot).abs().idxmin(), "strike"]
        atm = g[g["strike"] == k]
        c = atm.loc[atm["type"] == "call", "iv"]
        p = atm.loc[atm["type"] == "put", "iv"]
        rows.append({"expiration": exp, "dte": int(g["dte"].iloc[0]), "atm_strike": float(k),
                     "atm_iv_call": float(c.iloc[0]) if len(c) else np.nan, "atm_iv_put": float(p.iloc[0]) if len(p) else np.nan,
                     "atm_iv": float(atm["iv"].mean()), "n_with_iv": int(len(g))})
    return pd.DataFrame(rows)


def skew_25d(chain: pd.DataFrame) -> pd.DataFrame:
    """Per expiration: IV of the ~25Δ put minus IV of the ~25Δ call (positive = puts richer, the usual equity skew)."""
    rows = []
    for exp, g in _with_iv(chain).groupby("expiration", sort=True):
        g = g[g["delta"].notna()]
        puts, calls = g[g["type"] == "put"], g[g["type"] == "call"]
        if puts.empty or calls.empty:
            continue
        p = puts.loc[(puts["delta"] + 0.25).abs().idxmin()]
        c = calls.loc[(calls["delta"] - 0.25).abs().idxmin()]
        rows.append({"expiration": exp, "dte": int(g["dte"].iloc[0]), "put25_strike": float(p["strike"]), "put25_iv": float(p["iv"]),
                     "call25_strike": float(c["strike"]), "call25_iv": float(c["iv"]), "skew25": float(p["iv"] - c["iv"])})
    return pd.DataFrame(rows)


def interpolate_iv(term: pd.DataFrame, days: int = 30) -> float:
    """Constant-maturity IV by linear interpolation of total variance between the two bracketing expirations."""
    t = term.dropna(subset=["atm_iv"]).sort_values("dte")
    t = t[t["dte"] > 0]
    if t.empty:
        return float("nan")
    if days <= t["dte"].iloc[0]:
        return float(t["atm_iv"].iloc[0])
    if days >= t["dte"].iloc[-1]:
        return float(t["atm_iv"].iloc[-1])
    hi = t[t["dte"] >= days].iloc[0]
    lo = t[t["dte"] < days].iloc[-1]
    v_lo, v_hi = lo["atm_iv"] ** 2 * lo["dte"], hi["atm_iv"] ** 2 * hi["dte"]
    w = (days - lo["dte"]) / (hi["dte"] - lo["dte"])
    var = v_lo + w * (v_hi - v_lo)
    return float(math.sqrt(max(var, 0) / days))


def iv_rank(history: pd.Series, current: float, window: int = 252, min_days: int = 5) -> tuple[float, float]:
    """IV rank = where current sits between the window's min and max (0–100); percentile = share of days below current.
    NaN until `min_days` of history exist, so a one-day-old tracker does not report a meaningless 50."""
    h = pd.Series(history).dropna().astype(float).tail(window)
    if len(h) < min_days or current is None or (isinstance(current, float) and math.isnan(current)):
        return float("nan"), float("nan")
    lo, hi = h.min(), h.max()
    rank = (current - lo) / (hi - lo) * 100 if hi > lo else 50.0
    pct = float((h < current).mean() * 100)
    return float(min(max(rank, 0), 100)), pct


def surface(chain: pd.DataFrame, edges=MONEYNESS_EDGES) -> pd.DataFrame:
    """Expiration × moneyness-bucket mean IV (OTM side: puts below spot, calls above), as a long table."""
    g = _with_iv(chain).copy()
    g = g[((g["type"] == "put") & (g["moneyness"] <= 1.0)) | ((g["type"] == "call") & (g["moneyness"] > 1.0))]
    if g.empty:
        return pd.DataFrame(columns=["expiration", "dte", "bucket", "iv", "n"])
    labels = [f"{a:.2f}–{b:.2f}" for a, b in zip(edges[:-1], edges[1:])]
    g["bucket"] = pd.cut(g["moneyness"], bins=edges, labels=labels, include_lowest=True)
    out = g.groupby(["expiration", "dte", "bucket"], observed=True)["iv"].agg(["mean", "size"]).reset_index()
    return out.rename(columns={"mean": "iv", "size": "n"})
