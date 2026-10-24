from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest

from moonape.analytics import chain as chainmod
from moonape.analytics import gex as gexmod
from moonape.analytics import iv as ivmod
from moonape.analytics import maxpain, metrics
from moonape.sources import alpaca

ASOF = datetime(2026, 10, 23, 15, 30, tzinfo=timezone.utc)


def tiny_chain():
    """Three strikes, one expiry. Hand computation:
    calls OI: 20→100, 25→50, 30→10 ; puts OI: 20→10, 25→50, 30→100
    pain(20) = calls 0 + puts: 50·5 + 100·10 = 1250
    pain(25) = calls: 100·5 = 500 + puts: 100·5 = 500 → 1000
    pain(30) = calls: 100·10 + 50·5 = 1250 + puts 0 → 1250
    → max pain = 25
    """
    rows = []
    for k, c_oi, p_oi in ((20, 100, 10), (25, 50, 50), (30, 10, 100)):
        for typ, oi in (("call", c_oi), ("put", p_oi)):
            rows.append({"snapshot_ts": ASOF, "symbol": f"X{k}{typ}", "underlying": "X", "expiration": date(2026, 11, 20), "dte": 28,
                         "strike": float(k), "type": typ, "moneyness": k / 25, "spot": 25.0, "bid": 1.0, "ask": 1.1, "mid": 1.05, "last": 1.0,
                         "day_volume": 10, "iv": 0.8, "delta": 0.5 if typ == "call" else -0.5, "gamma": 0.05, "theta": -0.01, "vega": 0.02,
                         "rho": 0.0, "open_interest": oi, "open_interest_date": date(2026, 10, 22), "feed": "indicative"})
    return pd.DataFrame(rows)


def test_max_pain_hand_computed():
    ch = tiny_chain()
    pc = maxpain.pain_curve(ch).set_index("strike")["pain"]
    assert pc.to_dict() == {20.0: 1250.0, 25.0: 1000.0, 30.0: 1250.0}
    assert maxpain.max_pain(ch) == 25.0
    t = maxpain.max_pain_table(ch)
    assert t.loc[0, "call_wall"] == 20.0 and t.loc[0, "put_wall"] == 30.0
    assert t.loc[0, "pc_oi"] == pytest.approx(160 / 160)


def test_max_pain_nan_without_oi():
    ch = tiny_chain()
    ch["open_interest"] = np.nan
    assert np.isnan(maxpain.max_pain(ch))


def test_parse_occ():
    assert alpaca.parse_occ("GME251121C00025000") == {"root": "GME", "expiration": date(2025, 11, 21), "type": "call", "strike": 25.0}
    assert alpaca.parse_occ("SPY260320P00612500")["strike"] == 612.5
    with pytest.raises(ValueError):
        alpaca.parse_occ("GME")


def fixture_chain(http):
    raw = alpaca.option_chain(http)
    contracts = alpaca.option_contracts(http, asof=ASOF.date())
    return chainmod.tidy_chain(raw, contracts, spot=24.60, asof=ASOF)


def test_fixture_chain_joins_oi_and_filters(http):
    ch = fixture_chain(http)
    assert len(ch) == 228
    assert ch["open_interest"].notna().mean() > 0.95
    assert (ch["dte"] >= 0).all()
    # 0DTE contracts carry no IV (Alpaca rule, reproduced by the fixture)
    assert ch.loc[ch["dte"] == 0, "iv"].isna().all()
    assert ch.loc[ch["dte"] > 0, "iv"].notna().mean() > 0.9


def test_term_structure_sorted_and_iv30_bracketed(http):
    ch = fixture_chain(http)
    term = ivmod.term_structure(ch)
    assert list(term["dte"]) == sorted(term["dte"]) and (term["dte"] > 0).all()
    assert term["atm_iv"].between(0.3, 3.0).all()
    iv30 = ivmod.interpolate_iv(term, 30)
    lo = term[term["dte"] < 30]["atm_iv"].iloc[-1]
    hi = term[term["dte"] >= 30]["atm_iv"].iloc[0]
    assert min(lo, hi) - 1e-9 <= iv30 <= max(lo, hi) + 1e-9
    # short-dated richer in the fixture → downward sloping term
    assert term["atm_iv"].iloc[0] > term["atm_iv"].iloc[-1]


def test_skew_is_positive_puts_richer(http):
    sk = ivmod.skew_25d(fixture_chain(http))
    assert not sk.empty and (sk["skew25"] > 0).all()


def test_iv_rank_and_percentile():
    hist = pd.Series([0.5, 0.6, 0.7, 0.8, 0.9])
    rank, pct = ivmod.iv_rank(hist, 0.7)
    assert rank == pytest.approx(50.0) and pct == pytest.approx(40.0)
    assert all(np.isnan(v) for v in ivmod.iv_rank(pd.Series(dtype=float), 0.7))


def test_surface_buckets(http):
    s = ivmod.surface(fixture_chain(http))
    assert {"expiration", "bucket", "iv", "n"} <= set(s.columns) and len(s) > 10


def test_gex_zero_gamma_between_walls(http):
    ch = fixture_chain(http)
    g = gexmod.gex_by_strike(ch)
    assert (g["call_gex"] >= 0).all() and (g["put_gex"] <= 0).all()
    zg = gexmod.zero_gamma(g)
    assert 15 < zg < 35


def test_chain_metrics_row(http):
    ch = fixture_chain(http)
    m = metrics.chain_metrics(ch, 24.60, ASOF)
    assert len(m) == 1
    r = m.iloc[0]
    assert r["front_dte"] > 0 and 15 <= r["front_max_pain"] <= 35
    assert r["n_contracts"] == 228 and r["pc_oi"] > 0 and not np.isnan(r["iv30"])
