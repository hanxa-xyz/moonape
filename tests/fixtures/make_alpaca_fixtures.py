"""Synthetic Alpaca responses in the documented shapes, priced with Black-Scholes so IV/Greek views are internally consistent.

Run `make fixtures` to regenerate. The clock timestamp is the fixture's "now"; expirations are relative to it.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "alpaca"
NOW = datetime(2026, 10, 23, 15, 30, tzinfo=timezone.utc)  # 11:30 ET, a Friday
SPOT = 24.60
R = 0.04
rng = np.random.default_rng(7)


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def npdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs(S, K, T, sigma, call: bool):
    if T <= 0 or sigma <= 0:
        intrinsic = max(S - K, 0) if call else max(K - S, 0)
        return intrinsic, None
    d1 = (math.log(S / K) + (R + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if call:
        price = S * ncdf(d1) - K * math.exp(-R * T) * ncdf(d2)
        delta = ncdf(d1)
        rho = K * T * math.exp(-R * T) * ncdf(d2) / 100
        theta = (-S * npdf(d1) * sigma / (2 * math.sqrt(T)) - R * K * math.exp(-R * T) * ncdf(d2)) / 365
    else:
        price = K * math.exp(-R * T) * ncdf(-d2) - S * ncdf(-d1)
        delta = ncdf(d1) - 1
        rho = -K * T * math.exp(-R * T) * ncdf(-d2) / 100
        theta = (-S * npdf(d1) * sigma / (2 * math.sqrt(T)) + R * K * math.exp(-R * T) * ncdf(-d2)) / 365
    gamma = npdf(d1) / (S * sigma * math.sqrt(T))
    vega = S * npdf(d1) * math.sqrt(T) / 100
    return price, {"delta": round(delta, 6), "gamma": round(gamma, 6), "theta": round(theta, 6), "vega": round(vega, 6), "rho": round(rho, 6)}


def occ(root, exp, cp, strike):
    return f"{root}{exp:%y%m%d}{cp}{int(round(strike * 1000)):08d}"


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    today = NOW.date()
    # expirations relative to the fixture clock: 0DTE, two weeklies, a monthly, two quarterlies
    exps = [today + timedelta(days=d) for d in (0, 7, 14, 35, 63, 119)]
    strikes = [10, 12.5, 15, 17.5, 20, 21, 22, 23, 24, 25, 26, 27, 28, 30, 32.5, 35, 40, 45, 50]

    # --- clock / calendar
    (OUT / "clock.json").write_text(json.dumps({
        "timestamp": iso(NOW), "is_open": True,
        "next_open": iso(datetime(2026, 10, 26, 13, 30, tzinfo=timezone.utc)),
        "next_close": iso(datetime(2026, 10, 23, 20, 0, tzinfo=timezone.utc))}, indent=1))
    (OUT / "calendar.json").write_text(json.dumps([{
        "date": today.isoformat(), "open": "09:30", "close": "16:00",
        "session_open": "0400", "session_close": "2000", "settlement_date": (today + timedelta(days=3)).isoformat()}], indent=1))

    # --- stock snapshots
    def snap(sym, px, prev, vol):
        return {
            "latestTrade": {"t": iso(NOW), "x": "V", "p": px, "s": 100, "c": ["@"], "i": 1, "z": "C"},
            "latestQuote": {"t": iso(NOW), "ax": "V", "ap": round(px + 0.01, 2), "as": 5, "bx": "V", "bp": round(px - 0.01, 2), "bs": 7, "c": ["R"], "z": "C"},
            "minuteBar": {"t": iso(NOW.replace(second=0)), "o": px, "h": px + 0.05, "l": px - 0.05, "c": px, "v": 1200, "n": 30, "vw": px},
            "dailyBar": {"t": iso(NOW.replace(hour=4, minute=0)), "o": prev + 0.2, "h": px + 0.6, "l": prev - 0.3, "c": px, "v": vol, "n": 9000, "vw": px - 0.1},
            "prevDailyBar": {"t": iso(NOW.replace(hour=4, minute=0) - timedelta(days=1)), "o": prev - 0.1, "h": prev + 0.4, "l": prev - 0.5, "c": prev, "v": vol * 2, "n": 15000, "vw": prev},
        }
    (OUT / "stock_snapshots.json").write_text(json.dumps({"GME": snap("GME", SPOT, 23.9, 2_400_000), "SPY": snap("SPY", 612.3, 609.8, 38_000_000)}, indent=1))

    # --- stock bars (random walks)
    def walk(start, n, step, vol):
        p = start
        out = []
        for _ in range(n):
            o = p
            p = max(1.0, p * (1 + rng.normal(0, step)))
            h, lo = max(o, p) * (1 + abs(rng.normal(0, step / 2))), min(o, p) * (1 - abs(rng.normal(0, step / 2)))
            out.append((round(o, 2), round(h, 2), round(lo, 2), round(p, 2), int(vol * (1 + abs(rng.normal(0, 0.4))))))
        return out

    daily = {}
    for sym, start, vol in (("GME", 21.0, 3_000_000), ("SPY", 560.0, 40_000_000)):
        bars = []
        d = today - timedelta(days=420)
        for o, h, lo, c, v in walk(start, 300, 0.03 if sym == "GME" else 0.008, vol):
            while d.weekday() >= 5:
                d += timedelta(days=1)
            bars.append({"t": f"{d.isoformat()}T04:00:00Z", "o": o, "h": h, "l": lo, "c": c, "v": v, "n": 1000, "vw": round((o + c) / 2, 2)})
            d += timedelta(days=1)
        daily[sym] = bars
    (OUT / "stock_bars_1Day.json").write_text(json.dumps({"bars": daily, "next_page_token": None}))
    intra = {}
    for sym, start, vol in (("GME", 23.9, 60_000), ("SPY", 609.8, 900_000)):
        t0 = NOW.replace(hour=13, minute=30) - timedelta(days=4)
        bars = []
        for o, h, lo, c, v in walk(start, 26 * 4, 0.004 if sym == "GME" else 0.001, vol):
            if t0.hour >= 20:
                t0 = (t0 + timedelta(days=1)).replace(hour=13, minute=30)
                while t0.weekday() >= 5:
                    t0 += timedelta(days=1)
            bars.append({"t": iso(t0), "o": o, "h": h, "l": lo, "c": c, "v": v, "n": 200, "vw": round((o + c) / 2, 2)})
            t0 += timedelta(minutes=15)
        intra[sym] = bars
    (OUT / "stock_bars_15Min.json").write_text(json.dumps({"bars": intra, "next_page_token": None}))

    # --- options: contracts (OI) + chain snapshots (quotes, greeks, IV)
    contracts, snapshots = [], {}
    for exp in exps:
        T = max((exp - today).days, 0) / 365
        dte = (exp - today).days
        for K in strikes:
            m = math.log(K / SPOT)
            base = 0.85 + 0.25 * math.exp(-dte / 40)  # short-dated richer
            sigma = base + 0.35 * max(-m, 0) + 0.12 * max(m, 0) + 0.05 * m * m  # put skew, mild call wing
            for cp, is_call in (("C", True), ("P", False)):
                sym = occ("GME", exp, cp, K)
                # OI: put wall at 20, call wall at 30, decaying with distance; more OI on the monthly
                if is_call:
                    oi = int(4000 * math.exp(-abs(K - 30) / 6) + 300)
                else:
                    oi = int(5000 * math.exp(-abs(K - 20) / 5) + 200)
                if dte in (35, 119):
                    oi = int(oi * 2.2)
                if dte == 0:
                    oi = int(oi * 0.5)
                price, greeks = bs(SPOT, K, T, sigma, is_call)
                spread = max(0.01, 0.04 * price)
                bid, ask = round(max(price - spread / 2, 0), 2), round(price + spread / 2, 2)
                deep = (is_call and K >= 45) or ((not is_call) and K <= 10)
                if deep and dte <= 14:
                    bid = 0.0  # zero bid → no greeks, per Alpaca's rule
                vol = int(max(0, rng.normal(oi * 0.12, oi * 0.05)))
                contracts.append({
                    "id": f"id-{sym}", "symbol": sym, "name": f"GME {exp:%b %d %Y} {K} {'Call' if is_call else 'Put'}", "status": "active",
                    "tradable": True, "expiration_date": exp.isoformat(), "root_symbol": "GME", "underlying_symbol": "GME",
                    "underlying_asset_id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415", "type": "call" if is_call else "put", "style": "american",
                    "strike_price": f"{K}", "multiplier": "100", "size": "100", "open_interest": str(oi),
                    "open_interest_date": (today - timedelta(days=1)).isoformat(), "close_price": f"{price:.2f}",
                    "close_price_date": (today - timedelta(days=1)).isoformat(), "ppind": False,
                })
                s = {
                    "latestQuote": {"ap": ask, "as": 12, "ax": "C", "bp": bid, "bs": 10, "bx": "C", "c": "A", "t": iso(NOW)},
                    "latestTrade": {"c": "I", "p": round((bid + ask) / 2, 2), "s": 3, "t": iso(NOW - timedelta(minutes=16)), "x": "C"},
                    "dailyBar": {"t": iso(NOW.replace(hour=4, minute=0)), "o": round(price * 0.98, 2), "h": round(price * 1.05, 2),
                                 "l": round(price * 0.95, 2), "c": round(price, 2), "v": vol, "n": max(1, vol // 7), "vw": round(price, 2)},
                    "prevDailyBar": {"t": iso(NOW.replace(hour=4, minute=0) - timedelta(days=1)), "o": round(price * 0.97, 2),
                                     "h": round(price * 1.03, 2), "l": round(price * 0.94, 2), "c": round(price * 0.99, 2), "v": vol * 2,
                                     "n": max(1, vol // 4), "vw": round(price, 2)},
                }
                if greeks is not None and bid > 0 and dte > 0:
                    s["greeks"] = greeks
                    s["impliedVolatility"] = round(sigma, 6)
                snapshots[sym] = s
    (OUT / "option_contracts.json").write_text(json.dumps({"option_contracts": contracts, "next_page_token": None}))
    (OUT / "option_chain.json").write_text(json.dumps({"snapshots": snapshots, "next_page_token": None}))
    print(f"wrote {len(contracts)} contracts, {len(snapshots)} snapshots, {len(exps)} expirations → {OUT}")


if __name__ == "__main__":
    main()
