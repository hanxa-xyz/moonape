"""Max pain and open-interest structure per expiration.

Max pain = the expiration price S (searched over listed strikes) that minimises what option holders would be paid:
    Pain(S) = Σ_K OI_call(K)·max(S−K, 0) + Σ_K OI_put(K)·max(K−S, 0)
Uses open interest (prior-day), never volume. Expirations with no OI get NaN.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def pain_curve(exp_chain: pd.DataFrame) -> pd.DataFrame:
    """Pain at each listed strike for one expiration. Columns: strike, pain, call_pain, put_pain."""
    calls = exp_chain[exp_chain["type"] == "call"]
    puts = exp_chain[exp_chain["type"] == "put"]
    strikes = np.sort(exp_chain["strike"].unique())
    ck, co = calls["strike"].to_numpy(float), calls["open_interest"].fillna(0).to_numpy(float)
    pk, po = puts["strike"].to_numpy(float), puts["open_interest"].fillna(0).to_numpy(float)
    S = strikes[:, None]
    call_pain = (np.maximum(S - ck[None, :], 0) * co[None, :]).sum(axis=1) if len(ck) else np.zeros(len(strikes))
    put_pain = (np.maximum(pk[None, :] - S, 0) * po[None, :]).sum(axis=1) if len(pk) else np.zeros(len(strikes))
    return pd.DataFrame({"strike": strikes, "call_pain": call_pain, "put_pain": put_pain, "pain": call_pain + put_pain})


def max_pain(exp_chain: pd.DataFrame) -> float:
    if exp_chain["open_interest"].fillna(0).sum() <= 0:
        return float("nan")
    pc = pain_curve(exp_chain)
    return float(pc.loc[pc["pain"].idxmin(), "strike"])


def _wall(df: pd.DataFrame, typ: str) -> float:
    d = df[(df["type"] == typ) & df["open_interest"].notna()]
    if d.empty or d["open_interest"].sum() <= 0:
        return float("nan")
    return float(d.loc[d["open_interest"].idxmax(), "strike"])


def max_pain_table(chain: pd.DataFrame) -> pd.DataFrame:
    """One row per expiration: max_pain, OI/volume by side, P/C ratios, call and put walls (largest-OI strikes)."""
    rows = []
    for exp, g in chain.groupby("expiration", sort=True):
        calls, puts = g[g["type"] == "call"], g[g["type"] == "put"]
        c_oi, p_oi = calls["open_interest"].fillna(0).sum(), puts["open_interest"].fillna(0).sum()
        c_v, p_v = calls["day_volume"].fillna(0).sum(), puts["day_volume"].fillna(0).sum()
        rows.append({
            "expiration": exp, "dte": int(g["dte"].iloc[0]), "max_pain": max_pain(g), "spot": float(g["spot"].iloc[0]),
            "call_oi": int(c_oi), "put_oi": int(p_oi), "pc_oi": (p_oi / c_oi) if c_oi else np.nan,
            "call_vol": int(c_v), "put_vol": int(p_v), "pc_vol": (p_v / c_v) if c_v else np.nan,
            "call_wall": _wall(g, "call"), "put_wall": _wall(g, "put"), "n_contracts": int(len(g)),
            "oi_date": g["open_interest_date"].dropna().max() if g["open_interest_date"].notna().any() else None,
        })
    out = pd.DataFrame(rows)
    if not out.empty:
        out["max_pain_vs_spot_pct"] = (out["max_pain"] / out["spot"] - 1) * 100
    return out


def strike_table(exp_chain: pd.DataFrame) -> pd.DataFrame:
    """Per strike for one expiration: call/put OI, volume, IV, mid; plus the pain curve. Feeds the OI-by-strike chart."""
    piv = exp_chain.pivot_table(index="strike", columns="type", values=["open_interest", "day_volume", "iv", "mid", "delta", "gamma"], aggfunc="first")
    piv.columns = [f"{t}_{m}".replace("open_interest", "oi").replace("day_volume", "vol") for m, t in piv.columns]
    piv = piv.reset_index()
    return piv.merge(pain_curve(exp_chain), on="strike", how="left")
