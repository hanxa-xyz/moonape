# moonape 🌙 — GME study tracker

Scheduled collectors (GitHub Actions) + a static dashboard (GitHub Pages at **moonape.hanxa.xyz**) for studying GME:

| what | source | cadence |
|---|---|---|
| GME and SPY price, day bar, prev close | Alpaca Market Data `/v2/stocks/snapshots` (IEX, free) | every 30 min in market hours |
| **Whole options chain**: bid/ask, last, day volume, **Greeks, IV** per contract | Alpaca `/v1beta1/options/snapshots/GME` (indicative feed, free) | every 30 min in market hours |
| **Open interest** per contract (prior day) | Alpaca Trading API `/v2/options/contracts` | daily + first run of the day |
| **Max pain**, call/put walls, P/C ratios, **GEX** and zero-gamma, **IV term structure, 25Δ skew, IV30, IV rank, surface** | computed from the two above | every snapshot |
| Newest r/Superstonk posts + **Due Diligence** flair | Reddit OAuth (script app) or Arctic Shift (keyless) | hourly, 7 days |
| SEC filings: GameStop, Ryan Cohen, Keith Gill; 13F-HR filers holding GME | EDGAR submissions JSON + full-text search | daily |
| Treasury par curve (2Y/10Y/30Y, 10Y−2Y) | US Treasury CSV (keyless, same-day) + FRED history | daily |
| USD/JPY, DXY, intraday yields | Yahoo chart JSON (keyless) | every 30 min |
| FINRA off-exchange short volume, OCC option volume by exchange | FINRA CDN, OCC marketdata (keyless) | daily |

Raw rows land as parquet in `data/` (one file per run, compacted per day) and are the study dataset: `moonape db --sql "select … from option_chain"`.

## Start tracking

**You need only Alpaca keys to start.** Everything else runs keyless (Treasury, Yahoo, Arctic Shift, EDGAR, FINRA, OCC) or is optional (FRED, Reddit).

1. Alpaca: sign up at app.alpaca.markets → *Paper trading* → **Generate API keys** (free Basic data plan). Put them in `.env` as `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`.
2. Optional, FRED: fredaccount.stlouisfed.org → API Keys → `FRED_API_KEY` (yield/yen history; the Treasury CSV covers the daily curve without it).
3. Optional, Reddit: reddit.com/prefs/apps → *create another app* → type **script**, redirect `http://localhost` → `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`. Until then Arctic Shift supplies the same posts.
4. `SEC_USER_AGENT="moonape you@example.com"` — EDGAR requires a contact address in the User-Agent.

```bash
cp .env.example .env   # fill in the keys
make setup && make test
make collect           # one real run of every collector → data/ and site/data
make serve             # dashboard at http://localhost:8787
make backfill          # history: GME/SPY bars since 2016, Treasury, FRED, EDGAR, DD posts (1y), FINRA (60d), OCC (30d)
make secrets           # gh secret set -f .env → GitHub Actions takes over
```

Then trigger the workflows once (`gh workflow run intraday.yml -f force=true`, `gh workflow run reddit.yml`, `gh workflow run daily.yml`) and watch `gh run list`.

### Schedules (UTC crons; the intraday job checks Alpaca's calendar and exits when the market is closed)
- `intraday.yml` — `7,37 13-21 * * 1-5` (09:30–16:00 ET in EDT and EST, plus one post-close snapshot)
- `reddit.yml` — `15 * * * *`
- `daily.yml` — `45 22 * * 1-5` (contracts/OI, Treasury, FRED, FINRA, OCC, EDGAR, compaction); `-f backfill=true` for history
- `pages.yml` — deploys `site/` on every push that touches it; `ci.yml` — ruff + pytest + the whole pipeline on fixtures

### Dashboard: moonape.hanxa.xyz
DNS (Squarespace → hanxa.xyz → DNS settings): `CNAME  moonape  →  hanxa-xyz.github.io`. Then in the repo: Settings → Pages → custom domain `moonape.hanxa.xyz`, enforce HTTPS (or `gh api -X PUT repos/hanxa-xyz/moonape/pages -f cname=moonape.hanxa.xyz`).
Until then the site is at https://hanxa-xyz.github.io/moonape/.

## Alpaca endpoints used (and what the free plan gives you)

| REST | alpaca-py | plan notes |
|---|---|---|
| `GET /v2/clock`, `/v2/calendar` (paper-api) | `TradingClient.get_clock()`, `.get_calendar()` | — |
| `GET /v2/options/contracts?underlying_symbols=GME&expiration_date_gte&lte&limit=10000` | `TradingClient.get_option_contracts(GetOptionContractsRequest)` | **only OI source**; without an explicit expiry window you get this week only |
| `GET /v2/stocks/snapshots?symbols=GME,SPY&feed=iex` | `StockHistoricalDataClient.get_stock_snapshot()` | `iex` real-time; `delayed_sip` consolidated 15-min late; `sip` needs Algo Trader Plus |
| `GET /v2/stocks/bars?timeframe=1Day&feed=sip&end=<now−16m>` | `.get_stock_bars(StockBarsRequest)` | SIP history is free when `end` ≥ 15 min old; since 2016 |
| `GET /v1beta1/options/snapshots/GME?feed=indicative&limit=1000` | `OptionHistoricalDataClient.get_option_chain(OptionChainRequest)` | Greeks + IV included; **no OI**; Greeks null for 0DTE and zero-bid contracts; `opra` feed = $99/mo |
| `GET /v1beta1/options/bars` | `.get_option_bars()` | history since 2024-02 (used by the IV-history backfill follow-up) |

Alpaca has no FX or yield-curve data (its 2026 fixed-income quotes are T-bills for Broker API partners), hence Treasury/FRED/Yahoo.

## Data dictionary (one row = …)

| dataset | grain | key columns |
|---|---|---|
| `stock_snapshots` | symbol × fetch | ts, price, bid/ask, day_*, prev_close |
| `stock_bars` | symbol × timeframe × bar | t, open/high/low/close/volume |
| `option_contracts` | contract × fetch | expiration, strike, type, open_interest, open_interest_date |
| `option_chain` | contract × snapshot | snapshot_ts, dte, moneyness, bid/ask/mid, day_volume, iv, delta/gamma/theta/vega/rho, open_interest |
| `chain_metrics` | snapshot | spot, front/monthly max pain, walls, pc_oi, pc_vol, iv30, iv60, skew25_front, net_gex, zero_gamma |
| `macro_intraday` | ticker × ts × interval | close (yields in %, FX level) |
| `treasury_curve` | date × tenor | yield |
| `fred` | series × date | value |
| `reddit_posts` | post × fetch (dedupe by id) | created_utc, title, flair, score, num_comments, selftext |
| `edgar_filings` | filing × fetch (dedupe by accession) | entity, form, filing_date, url |
| `edgar_13f` | 13F filing × fetch | filer, cik, file_date, period_ending |
| `finra_short_volume` | date × symbol | short_volume, total_volume, short_share |
| `occ_volume` | date × side × account_type × exchange | quantity |

## Definitions
- **Max pain** per expiration: strike *S* minimising Σ OI_call·max(S−K,0) + Σ OI_put·max(K−S,0). OI is prior-day (OCC publishes once daily).
- **IV30**: ATM IV interpolated to 30 days in total variance between the bracketing expirations. **IV rank** = position between trailing-252-day min and max; **percentile** = share of days below.
- **GEX**: Σ gamma·OI·100·S²·1% with calls positive and puts negative (dealer convention); zero-gamma = first strike where per-strike net GEX turns positive. A convention, not a measurement.
- **BOJ policy rate** is a dated constant in `config.py` (no fresh machine-readable source).

## Storage ceiling
~2.5k GME contracts × ~16 snapshots/day ≈ 1.5 MB/day of zstd parquet → the repo reaches ~1 GB in about 18 months. The Pages artifact excludes `data/`.
Moving `data/` to object storage (R2) or GitHub Releases is a change inside `store.py` only.

## Follow-ups
- IV history before the tracker started: invert Black-Scholes on Alpaca option bars (since 2024-02) so IV rank is meaningful on day one.
- 13F holding sizes from the information-table XML.
- Rigorous gamma flip (re-price gamma at each candidate spot level).
- BOJ statements scraper.
