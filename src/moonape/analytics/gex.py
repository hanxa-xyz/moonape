"""Gamma exposure by strike, dealer-positioning convention (dealers long calls, short puts), in $ per 1% move.

GEX_call(K) = Σ gamma·OI·100·S²·0.01 ; GEX_put(K) = −Σ gamma·OI·100·S²·0.01 ; net = call + put.
Zero-gamma (flip) = the strike where per-strike net GEX turns from negative (put-dominated, below spot) to positive
(call-dominated), linearly interpolated; the proxy dashboards quote. It is a convention, not a measurement: the
rigorous version re-prices gamma at each candidate spot level (follow-up).
"""
from __future__ import annotations

import pandas as pd


def gex_by_strike(chain: pd.DataFrame, expirations=None) -> pd.DataFrame:
    g = chain[chain["gamma"].notna() & chain["open_interest"].notna()].copy()
    if expirations is not None:
        g = g[g["expiration"].isin(expirations)]
    if g.empty:
        return pd.DataFrame(columns=["strike", "call_gex", "put_gex", "net_gex"])
    spot2 = g["spot"].astype(float) ** 2
    g["gex"] = g["gamma"] * g["open_interest"] * 100 * spot2 * 0.01
    g.loc[g["type"] == "put", "gex"] *= -1
    out = g.pivot_table(index="strike", columns="type", values="gex", aggfunc="sum").fillna(0.0)
    out = out.rename(columns={"call": "call_gex", "put": "put_gex"})
    for c in ("call_gex", "put_gex"):
        if c not in out:
            out[c] = 0.0
    out["net_gex"] = out["call_gex"] + out["put_gex"]
    return out.reset_index().sort_values("strike").reset_index(drop=True)


def zero_gamma(gex: pd.DataFrame) -> float:
    if gex.empty:
        return float("nan")
    k = gex["strike"].to_numpy(float)
    net = gex["net_gex"].to_numpy(float)
    for i in range(1, len(net)):
        if net[i - 1] < 0 <= net[i]:
            if net[i] == 0:
                return float(k[i])
            w = net[i - 1] / (net[i - 1] - net[i])
            return float(k[i - 1] + w * (k[i] - k[i - 1]))
    return float("nan")


def total_gex(gex: pd.DataFrame) -> float:
    return float(gex["net_gex"].sum()) if not gex.empty else float("nan")
