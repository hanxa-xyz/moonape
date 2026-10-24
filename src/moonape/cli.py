"""moonape CLI: collect {intraday,reddit,daily,all} · backfill · site · db · compact"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from moonape import config, store
from moonape.analytics import chain as chainmod
from moonape.analytics import metrics
from moonape.http import Http
from moonape.sources import alpaca, edgar, finra, fred, occ, reddit, treasury, yahoo

log = logging.getLogger("moonape")


def _now(http: Http) -> datetime:
    """Real UTC now, or the fixture clock's timestamp so fixture runs are deterministic."""
    if config.fixture_mode():
        return pd.Timestamp(alpaca.clock(http)["timestamp"]).to_pydatetime()
    return datetime.now(timezone.utc)


class Step:
    """Run one collector step; log and record failures instead of aborting the run."""

    def __init__(self):
        self.failed: list[str] = []
        self.rows: dict[str, int] = {}

    def run(self, name: str, fn, *, critical: bool = False):
        try:
            n = fn()
            self.rows[name] = int(n or 0)
            log.info("✓ %s (%s rows)", name, self.rows[name])
        except Exception as e:  # noqa: BLE001 - every failure is logged and summarised
            self.failed.append(name)
            log.error("✗ %s: %s", name, e, exc_info=log.isEnabledFor(logging.DEBUG))
            if critical:
                raise

    def summary(self) -> str:
        ok = ", ".join(f"{k}={v}" for k, v in self.rows.items())
        return f"ok: {ok or '-'}" + (f" | FAILED: {', '.join(self.failed)}" if self.failed else "")


# --- collectors ------------------------------------------------------------------------------------------
def _latest_contracts() -> pd.DataFrame:
    if not store.exists("option_contracts"):
        return pd.DataFrame()
    return store.read("option_contracts", "SELECT * FROM option_contracts WHERE fetched_at = (SELECT max(fetched_at) FROM option_contracts)")


def _contracts_fresh(now: datetime) -> bool:
    c = _latest_contracts()
    return not c.empty and pd.Timestamp(c["fetched_at"].iloc[0]).date() == now.date()


def collect_contracts(http: Http, now: datetime) -> int:
    df = alpaca.option_contracts(http, asof=now.date())
    store.append("option_contracts", df, now)
    return len(df)


def collect_intraday(http: Http, force: bool = False) -> Step:
    now = _now(http)
    st = Step()
    if not force:
        ok, why = alpaca.in_collection_window(http, now)
        if not ok:
            log.info("market closed: %s — nothing to do", why)
            return st

    def stocks():
        df = alpaca.stock_snapshots(http)
        store.append("stock_snapshots", df, now)
        return len(df)

    st.run("stock_snapshots", stocks, critical=True)
    spot_df = store.read("stock_snapshots", "SELECT price FROM stock_snapshots WHERE symbol='GME' ORDER BY fetched_at DESC LIMIT 1")
    spot = float(spot_df["price"].iloc[0]) if not spot_df.empty else float("nan")

    if not _contracts_fresh(now):
        st.run("option_contracts", lambda: collect_contracts(http, now))

    def chain():
        raw = alpaca.option_chain(http)
        tidy = chainmod.tidy_chain(raw, _latest_contracts(), spot, now)
        store.append("option_chain", tidy, now)
        store.append("chain_metrics", metrics.chain_metrics(tidy, spot, now), now)
        return len(tidy)

    st.run("option_chain", chain, critical=True)
    st.run("macro_intraday", lambda: _append_len("macro_intraday", yahoo.fetch_all(http), now))
    return st


def collect_reddit(http: Http) -> Step:
    now = _now(http)
    st = Step()
    st.run("reddit_posts", lambda: _append_len("reddit_posts", reddit.fetch_latest(http), now), critical=True)
    return st


def collect_daily(http: Http) -> Step:
    now = _now(http)
    today = now.date()
    st = Step()
    st.run("option_contracts", lambda: collect_contracts(http, now))
    st.run("treasury_curve", lambda: _append_len("treasury_curve", treasury.fetch_year(http, today.year), now))
    if fred.available():
        st.run("fred", lambda: _append_len("fred", fred.fetch_all(http, start=(today - timedelta(days=45)).isoformat()), now))
    else:
        log.info("FRED_API_KEY not set — skipping FRED (Treasury CSV covers the daily curve)")
    st.run("finra_short_volume", lambda: _append_len("finra_short_volume", finra.fetch_recent(http, today, days=5), now))
    st.run("occ_volume", lambda: _append_len("occ_volume", occ.fetch_recent(http, today, days=5), now))
    st.run("edgar_filings", lambda: _append_len("edgar_filings", edgar.all_submissions(http), now))
    st.run("edgar_13f", lambda: _append_len("edgar_13f", edgar.holders_13f(http, today - timedelta(days=120), today), now))
    st.run("macro_daily", lambda: _append_len("macro_intraday", yahoo.fetch_all(http, range_="5d", interval="1d"), now))
    st.run("compact", lambda: store.compact_all(before=today.isoformat()))
    return st


def backfill(http: Http, years: int = 10) -> Step:
    now = _now(http)
    today = now.date()
    st = Step()
    start = datetime(today.year - years, 1, 1, tzinfo=timezone.utc)
    st.run("stock_bars_1Day", lambda: _append_len("stock_bars", alpaca.stock_bars(http, config.STOCKS, "1Day", start), now, name="backfill_1Day"))
    st.run("stock_bars_15Min", lambda: _append_len("stock_bars", alpaca.stock_bars(http, config.STOCKS, "15Min", now - timedelta(days=90)), now,
                                                   name="backfill_15Min"))

    def treasury_years():
        n = 0
        for y in range(today.year - years, today.year + 1):
            try:
                n += _append_len("treasury_curve", treasury.fetch_year(http, y), now, name=f"backfill_{y}")
            except FileNotFoundError:
                pass
        return n

    st.run("treasury_curve", treasury_years)
    if fred.available():
        st.run("fred", lambda: _append_len("fred", fred.fetch_all(http, start=f"{today.year - years}-01-01"), now, name="backfill"))
    st.run("edgar_filings", lambda: _append_len("edgar_filings", edgar.all_submissions(http, include_older=True), now, name="backfill"))
    st.run("edgar_13f", lambda: _append_len("edgar_13f", edgar.holders_13f(http, today - timedelta(days=400), today, pages=10), now, name="backfill"))
    st.run("reddit_dd", lambda: _append_len("reddit_posts", reddit.backfill_dd(http, days=365), now, name="backfill_dd"))
    st.run("finra_short_volume", lambda: _append_len("finra_short_volume", finra.fetch_recent(http, today, days=60), now, name="backfill"))
    st.run("occ_volume", lambda: _append_len("occ_volume", occ.fetch_recent(http, today, days=30), now, name="backfill"))
    st.run("macro_daily", lambda: _append_len("macro_intraday", yahoo.fetch_all(http, range_="2y", interval="1d"), now, name="backfill_daily"))
    return st


def _append_len(dataset: str, df: pd.DataFrame, now: datetime, name: str | None = None) -> int:
    store.append(dataset, df, now, name=name)
    return 0 if df is None else len(df)


# --- entry point ---------------------------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="moonape", description=__doc__)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--fixture", action="store_true", help="serve recorded responses instead of the network (MOONAPE_FIXTURE=1)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="run collectors once")
    c.add_argument("what", choices=["intraday", "reddit", "daily", "all"])
    c.add_argument("--force", action="store_true", help="ignore the market-hours window")
    c.add_argument("--no-site", action="store_true", help="skip rebuilding site/data")
    b = sub.add_parser("backfill", help="history for every source that offers it")
    b.add_argument("--years", type=int, default=10)
    s = sub.add_parser("site", help="rebuild site/data/*.json from data/")
    s.add_argument("--out", default=None, help="output dir (default site/data)")
    d = sub.add_parser("db", help="row counts and freshness; or run SQL against the dataset views")
    d.add_argument("--sql", default=None)
    sub.add_parser("compact", help="merge past days' hourly files into one parquet per day")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
                        stream=sys.stderr)
    if a.fixture:
        os.environ["MOONAPE_FIXTURE"] = "1"
    http = Http()
    rc = 0
    try:
        if a.cmd == "collect":
            steps = []
            if a.what in ("intraday", "all"):
                steps.append(collect_intraday(http, force=a.force or a.what == "all"))
            if a.what in ("reddit", "all"):
                steps.append(collect_reddit(http))
            if a.what in ("daily", "all"):
                steps.append(collect_daily(http))
            for st in steps:
                log.info(st.summary())
            rc = 1 if any(st.failed for st in steps) else 0
            if not a.no_site:
                from moonape.build_site import build
                build()
        elif a.cmd == "backfill":
            st = backfill(http, a.years)
            log.info(st.summary())
            rc = 1 if st.failed else 0
        elif a.cmd == "site":
            from moonape.build_site import build
            build(a.out)
        elif a.cmd == "db":
            if a.sql:
                con = store.connect()
                print(con.execute(a.sql).df().to_string())
            else:
                print(store.summary().to_string(index=False))
        elif a.cmd == "compact":
            print(f"removed {store.compact_all()} files")
    finally:
        http.close()
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
