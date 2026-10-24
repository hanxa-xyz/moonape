"""data/ (parquet) → site/data/*.json: small aggregates the static dashboard renders. Never raw rows.

Every file is written even when its dataset is empty, so the page renders with partial data.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from moonape import config, store
from moonape.analytics import gex as gexmod
from moonape.analytics import iv as ivmod
from moonape.analytics import maxpain

log = logging.getLogger("moonape.site")


# --- json helpers ------------------------------------------------------------------------------------------
def _clean(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if (isinstance(v, float) and math.isnan(v)) or (isinstance(v, np.floating) and np.isnan(v)) else float(v)
    if isinstance(v, (pd.Timestamp, datetime)):
        return None if pd.isna(v) else pd.Timestamp(v).isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if v is pd.NaT:
        return None
    return v


DATE_COLS = {"expiration", "oi_date", "open_interest_date", "front_expiry", "monthly_expiry", "filing_date", "report_date", "file_date",
             "period_ending", "date", "prev_date", "close_price_date"}


def _dates(df: pd.DataFrame) -> pd.DataFrame:
    """Calendar-date columns come back from DuckDB as midnight timestamps; render them as YYYY-MM-DD."""
    df = df.copy()
    for c in df.columns:
        if c in DATE_COLS:
            df[c] = pd.to_datetime(df[c], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


def _day(v) -> str | None:
    return None if v is None or pd.isna(v) else pd.Timestamp(v).strftime("%Y-%m-%d")


def records(df: pd.DataFrame | None, cols=None) -> list[dict]:
    if df is None or df.empty:
        return []
    d = _dates(df[cols] if cols else df)
    return [{k: _clean(v) for k, v in row.items()} for row in d.to_dict(orient="records")]


def series(df: pd.DataFrame, x: str, y: str) -> list[list]:
    if df is None or df.empty:
        return []
    return [[_clean(a), _clean(b)] for a, b in zip(df[x], df[y]) if not (b is None or (isinstance(b, float) and math.isnan(b)))]


def _deep(o):
    if isinstance(o, dict):
        return {str(k): _deep(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_deep(v) for v in o]
    return _clean(o)


def write(out: Path, name: str, obj) -> None:
    """Strict JSON: NaN/NaT become null (json.dumps would otherwise emit `NaN`, which browsers reject)."""
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(_deep(obj), allow_nan=False, separators=(",", ":")))
    log.info("site: %s", name)


def q(con, sql: str) -> pd.DataFrame:
    try:
        return con.execute(sql).df()
    except Exception as e:  # noqa: BLE001 - a missing view just means no data yet
        log.debug("query skipped (%s): %s", e, sql[:80])
        return pd.DataFrame()


# --- builders -----------------------------------------------------------------------------------------------
def latest_chain(con) -> pd.DataFrame:
    return q(con, "SELECT * FROM option_chain WHERE snapshot_ts = (SELECT max(snapshot_ts) FROM option_chain)")


def build_tiles(con, chain, mp, term, hist, out):
    snaps = q(con, "SELECT * FROM stock_snapshots QUALIFY row_number() OVER (PARTITION BY symbol ORDER BY fetched_at DESC) = 1")
    stock = {}
    for _, r in snaps.iterrows():
        chg = (r["price"] / r["prev_close"] - 1) * 100 if r.get("prev_close") else None
        stock[r["symbol"]] = {"price": r["price"], "prev_close": r["prev_close"], "change_pct": chg, "ts": r["ts"], "day_volume": r["day_volume"],
                              "day_high": r["day_high"], "day_low": r["day_low"], "feed": r.get("feed")}
    tc = q(con, "SELECT * FROM treasury_curve QUALIFY row_number() OVER (PARTITION BY date, tenor ORDER BY fetched_at DESC) = 1")
    yields = {}
    if not tc.empty:
        last = tc[tc["date"] == tc["date"].max()].set_index("tenor")["yield"]
        yields = {"date": _day(tc["date"].max()), **{t: last.get(t) for t in ("3M", "2Y", "5Y", "10Y", "30Y")}}
        if last.get("10Y") is not None and last.get("2Y") is not None:
            yields["spread_10y2y"] = round(float(last["10Y"] - last["2Y"]), 3)
    macro = q(con, "SELECT ticker, close, ts FROM macro_intraday QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY ts DESC) = 1")
    mac = {r["ticker"]: {"value": r["close"], "ts": r["ts"]} for _, r in macro.iterrows()}
    opt = {}
    if not hist.empty:
        h = hist.iloc[-1]
        daily = hist.set_index("ts")["iv30"].resample("1D").last().dropna()
        rank, pct = ivmod.iv_rank(daily.iloc[:-1] if len(daily) > 1 else daily, float(h["iv30"]) if pd.notna(h["iv30"]) else None)
        h = _dates(hist.tail(1)).iloc[0]
        opt = {k: h.get(k) for k in ("ts", "spot", "front_expiry", "front_dte", "front_max_pain", "front_call_wall", "front_put_wall", "monthly_expiry",
                                     "monthly_max_pain", "pc_oi", "pc_vol", "iv30", "iv60", "atm_iv_front", "skew25_front", "net_gex", "zero_gamma",
                                     "oi_date", "n_contracts", "n_with_iv", "n_with_oi")}
        opt["iv_rank"], opt["iv_pct"], opt["iv_history_days"] = rank, pct, int(len(daily))
    sec = q(con, "SELECT entity, form, filing_date, url, description FROM edgar_filings QUALIFY row_number() OVER (PARTITION BY accession ORDER BY fetched_at DESC) = 1 "
                 "ORDER BY filing_date DESC, acceptance_dt DESC NULLS LAST LIMIT 1")
    rd = q(con, "SELECT title, created_utc, permalink, flair FROM reddit_posts WHERE flair ILIKE '%Due Diligence%' "
                "QUALIFY row_number() OVER (PARTITION BY id ORDER BY fetched_at DESC) = 1 ORDER BY created_utc DESC LIMIT 1")
    n_dd = q(con, "SELECT count(DISTINCT id) AS n FROM reddit_posts WHERE flair ILIKE '%Due Diligence%' AND created_utc > now() - INTERVAL 7 DAY")
    write(out, "tiles.json", {
        "stocks": stock, "yields": yields, "macro": mac, "boj": {"rate": config.BOJ_POLICY_RATE, "asof": config.BOJ_RATE_ASOF}, "options": opt,
        "sec": records(sec)[0] if not sec.empty else {}, "reddit": {**(records(rd)[0] if not rd.empty else {}), "n_dd_7d": int(n_dd["n"][0]) if not n_dd.empty else 0},
    })


def build_price_macro(con, out):
    snaps = q(con, "SELECT symbol, ts, price, day_close, prev_close FROM stock_snapshots WHERE ts > now() - INTERVAL 7 DAY ORDER BY ts")
    bars = q(con, "SELECT symbol, t, close, open, high, low, volume FROM stock_bars WHERE timeframe='1Day' "
                  "QUALIFY row_number() OVER (PARTITION BY symbol, t ORDER BY fetched_at DESC) = 1 ORDER BY t")
    bars15 = q(con, "SELECT symbol, t, close FROM stock_bars WHERE timeframe='15Min' QUALIFY row_number() OVER (PARTITION BY symbol, t ORDER BY fetched_at DESC) = 1 ORDER BY t")
    tc = q(con, "SELECT date, tenor, yield FROM treasury_curve QUALIFY row_number() OVER (PARTITION BY date, tenor ORDER BY fetched_at DESC) = 1 ORDER BY date")
    yd = []
    if not tc.empty:
        wide = tc.pivot(index="date", columns="tenor", values="yield").reset_index()
        if {"10Y", "2Y"} <= set(wide.columns):
            wide["spread_10y2y"] = wide["10Y"] - wide["2Y"]
        yd = records(wide[[c for c in ("date", "3M", "2Y", "5Y", "10Y", "30Y", "spread_10y2y") if c in wide.columns]])
    mi = q(con, "SELECT ticker, ts, close, interval FROM macro_intraday QUALIFY row_number() OVER (PARTITION BY ticker, ts, interval ORDER BY fetched_at DESC) = 1 ORDER BY ts")
    intr = {t: series(g[(g["interval"] != "1d") & (g["ts"] > g["ts"].max() - pd.Timedelta(days=7))], "ts", "close") for t, g in mi.groupby("ticker")} if not mi.empty else {}
    daily = {t: series(g[g["interval"] == "1d"], "ts", "close") for t, g in mi.groupby("ticker")} if not mi.empty else {}
    fred = q(con, "SELECT series_id, date, value FROM fred QUALIFY row_number() OVER (PARTITION BY series_id, date ORDER BY fetched_at DESC) = 1 ORDER BY date")
    write(out, "price_macro.json", {
        "intraday": {s: series(g, "ts", "price") for s, g in snaps.groupby("symbol")} if not snaps.empty else {},
        "bars15": {s: series(g, "t", "close") for s, g in bars15.groupby("symbol")} if not bars15.empty else {},
        "daily": {s: records(g, ["t", "open", "high", "low", "close", "volume"]) for s, g in bars.groupby("symbol")} if not bars.empty else {},
        "yields_daily": yd, "macro_intraday": intr, "macro_daily": daily,
        "fred": {s: series(g, "date", "value") for s, g in fred.groupby("series_id")} if not fred.empty else {},
    })


def build_options(con, chain, mp, hist, out):
    exps = {}
    if not chain.empty:
        for exp, g in chain.groupby("expiration", sort=True):
            st = maxpain.strike_table(g)
            gx = gexmod.gex_by_strike(g)
            st = st.merge(gx, on="strike", how="left")
            exps[_day(exp)] = {"dte": int(g["dte"].iloc[0]), "max_pain": maxpain.max_pain(g), "zero_gamma": gexmod.zero_gamma(gx),
                              "n": int(len(g)), "strikes": records(st)}
    gx_all = gexmod.gex_by_strike(chain) if not chain.empty else pd.DataFrame()
    finra = q(con, "SELECT date, symbol, short_volume, total_volume, short_share FROM finra_short_volume "
                   "QUALIFY row_number() OVER (PARTITION BY date, symbol ORDER BY fetched_at DESC) = 1 ORDER BY date")
    occ = q(con, "SELECT * FROM occ_volume QUALIFY row_number() OVER (PARTITION BY date, side, account_type, exchange ORDER BY fetched_at DESC) = 1")
    occ_ex, occ_acct, occ_daily = [], [], []
    if not occ.empty:
        last = occ[occ["date"] == occ["date"].max()]
        occ_ex = records(last.pivot_table(index="exchange", columns="side", values="quantity", aggfunc="sum").fillna(0).reset_index()
                         .sort_values("call", ascending=False) if "call" in last["side"].values else pd.DataFrame())
        occ_acct = records(last.pivot_table(index="account_type", columns="side", values="quantity", aggfunc="sum").fillna(0).reset_index())
        occ_daily = records(occ.pivot_table(index="date", columns="side", values="quantity", aggfunc="sum").fillna(0).reset_index())
    write(out, "options.json", {
        "snapshot_ts": chain["snapshot_ts"].iloc[0] if not chain.empty else None, "spot": float(chain["spot"].iloc[0]) if not chain.empty else None,
        "oi_date": _day(chain["open_interest_date"].dropna().max()) if not chain.empty and chain["open_interest_date"].notna().any() else None,
        "maxpain": records(mp), "expirations": exps,
        "gex_all": records(gx_all), "zero_gamma_all": gexmod.zero_gamma(gx_all) if not gx_all.empty else None,
        "history": records(hist.tail(2000)) if not hist.empty else [],
        "finra": records(finra[finra["symbol"] == "GME"]) if not finra.empty else [],
        "occ_by_exchange": occ_ex, "occ_by_account": occ_acct, "occ_daily": occ_daily,
    })


def build_iv(con, chain, term, hist, out):
    skew = ivmod.skew_25d(chain) if not chain.empty else pd.DataFrame()
    surf = ivmod.surface(chain) if not chain.empty else pd.DataFrame()
    surface = {}
    if not surf.empty:
        piv = surf.pivot_table(index="expiration", columns="bucket", values="iv", aggfunc="mean", observed=True)
        piv = piv.reindex(columns=[c for c in [f"{a:.2f}–{b:.2f}" for a, b in zip(ivmod.MONEYNESS_EDGES[:-1], ivmod.MONEYNESS_EDGES[1:])] if c in piv.columns])
        surface = {"expirations": [_day(i) for i in piv.index], "buckets": list(piv.columns),
                   "z": [[_clean(v) for v in row] for row in piv.to_numpy()]}
    iv30_hist = series(hist, "ts", "iv30") if not hist.empty else []
    daily = []
    if not hist.empty:
        d = hist.set_index("ts")["iv30"].resample("1D").last().dropna().reset_index()
        daily = series(d, "ts", "iv30")
    write(out, "iv.json", {"snapshot_ts": chain["snapshot_ts"].iloc[0] if not chain.empty else None, "term": records(term), "skew": records(skew),
                           "iv30_history": iv30_hist, "iv30_daily": daily, "surface": surface})


def build_reddit(con, out):
    posts = q(con, "SELECT id, created_utc, title, author, flair, score, num_comments, upvote_ratio, permalink, url, left(selftext, 320) AS preview, "
                   "length(selftext) AS selftext_len, source FROM reddit_posts QUALIFY row_number() OVER (PARTITION BY id ORDER BY fetched_at DESC) = 1 "
                   "ORDER BY created_utc DESC LIMIT 400")
    flairs = q(con, "SELECT flair, count(DISTINCT id) AS n FROM reddit_posts GROUP BY flair ORDER BY n DESC")
    write(out, "reddit.json", {"posts": records(posts), "flairs": records(flairs)})


def build_sec(con, out):
    f = q(con, "SELECT cik, entity, accession, form, filing_date, report_date, acceptance_dt, items, description, url, index_url FROM edgar_filings "
               "QUALIFY row_number() OVER (PARTITION BY accession ORDER BY fetched_at DESC) = 1 ORDER BY filing_date DESC, acceptance_dt DESC NULLS LAST LIMIT 400")
    h = q(con, "SELECT filer, cik, file_date, period_ending, form, url, total_hits FROM edgar_13f QUALIFY row_number() OVER (PARTITION BY adsh ORDER BY fetched_at DESC) = 1 "
               "ORDER BY file_date DESC LIMIT 200")
    counts = q(con, "SELECT entity, form, count(DISTINCT accession) AS n FROM edgar_filings GROUP BY 1, 2 ORDER BY n DESC")
    write(out, "sec.json", {"filings": records(f), "holders_13f": records(h), "counts": records(counts)})


def build(out_dir: str | Path | None = None) -> Path:
    out = Path(out_dir) if out_dir else Path(config.SITE_DATA)
    con = store.connect()
    chain = latest_chain(con)
    mp = maxpain.max_pain_table(chain) if not chain.empty else pd.DataFrame()
    term = ivmod.term_structure(chain) if not chain.empty else pd.DataFrame()
    hist = q(con, "SELECT * FROM chain_metrics QUALIFY row_number() OVER (PARTITION BY ts ORDER BY fetched_at DESC) = 1 ORDER BY ts")
    if not hist.empty:
        hist["ts"] = pd.to_datetime(hist["ts"], utc=True)
    build_tiles(con, chain, mp, term, hist, out)
    build_price_macro(con, out)
    build_options(con, chain, mp, hist, out)
    build_iv(con, chain, term, hist, out)
    build_reddit(con, out)
    build_sec(con, out)
    summ = store.summary()
    write(out, "meta.json", {
        "built_at": datetime.now(timezone.utc), "fixture": config.fixture_mode(), "version": "0.1.0",
        "datasets": {r["dataset"]: {"rows": int(r["rows"]), "latest_fetch": _clean(r["latest_fetch"]), "mb": r["mb"]} for _, r in summ.iterrows()},
        "boj": {"rate": config.BOJ_POLICY_RATE, "asof": config.BOJ_RATE_ASOF},
        "feeds": {"options": config.ALPACA_OPTION_FEED, "stocks": config.ALPACA_STOCK_FEED},
        "stale_after": {"intraday_min": 45, "reddit_min": 90, "daily_h": 30},
        "cutoff_7d": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),
    })
    con.close()
    return out
