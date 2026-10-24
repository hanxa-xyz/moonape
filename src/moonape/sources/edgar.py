"""SEC EDGAR: submissions JSON per CIK (near-real-time) and full-text search for 13F holders by CUSIP.

Rules: ≤ 10 requests/second, a User-Agent with a contact address, gzip accepted.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from moonape import config
from moonape.http import Http

log = logging.getLogger("moonape.edgar")
SUBMISSIONS = "https://data.sec.gov/submissions/{name}"
FTS = "https://efts.sec.gov/LATEST/search-index"
FILING_COLS = ["cik", "entity", "accession", "form", "filing_date", "report_date", "acceptance_dt", "items", "primary_doc",
               "description", "url", "index_url", "size", "is_xbrl"]


def _headers() -> dict:
    return {"User-Agent": config.SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}


def _rows(cik: str, entity: str, recent: dict) -> pd.DataFrame:
    n = len(recent.get("accessionNumber", []))
    if n == 0:
        return pd.DataFrame(columns=FILING_COLS)
    cik_int = int(cik)
    rows = []
    for i in range(n):
        acc = recent["accessionNumber"][i]
        nodash = acc.replace("-", "")
        doc = (recent.get("primaryDocument") or [""] * n)[i]
        rows.append({
            "cik": cik, "entity": entity, "accession": acc, "form": recent["form"][i],
            "filing_date": recent["filingDate"][i], "report_date": (recent.get("reportDate") or [""] * n)[i] or None,
            "acceptance_dt": (recent.get("acceptanceDateTime") or [""] * n)[i] or None,
            "items": (recent.get("items") or [""] * n)[i] or None, "primary_doc": doc or None,
            "description": (recent.get("primaryDocDescription") or [""] * n)[i] or None,
            "url": f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{nodash}/{doc}" if doc else None,
            "index_url": f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{nodash}/{acc}-index.htm",
            "size": (recent.get("size") or [None] * n)[i], "is_xbrl": bool((recent.get("isXBRL") or [0] * n)[i]),
        })
    df = pd.DataFrame(rows, columns=FILING_COLS)
    df["filing_date"] = pd.to_datetime(df["filing_date"]).dt.date
    df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce").dt.date
    df["acceptance_dt"] = pd.to_datetime(df["acceptance_dt"], errors="coerce", utc=True)
    return df


def submissions(http: Http, cik: str, include_older: bool = False) -> pd.DataFrame:
    js = http.get_json(SUBMISSIONS.format(name=f"CIK{cik}.json"), headers=_headers(), fixture=f"edgar/CIK{cik}")
    entity = js.get("name") or config.CIKS.get(cik, cik)
    frames = [_rows(cik, entity, js.get("filings", {}).get("recent", {}))]
    if include_older:
        for f in js.get("filings", {}).get("files", []):
            try:
                older = http.get_json(SUBMISSIONS.format(name=f["name"]), headers=_headers(), fixture=f"edgar/{f['name'].replace('.json', '')}")
                frames.append(_rows(cik, entity, older))
            except FileNotFoundError:
                log.info("edgar older file %s: no fixture, skipped", f["name"])
    return pd.concat(frames, ignore_index=True)


def all_submissions(http: Http, include_older: bool = False) -> pd.DataFrame:
    frames = []
    for cik in config.CIKS:
        try:
            frames.append(submissions(http, cik, include_older))
        except Exception as e:
            log.warning("edgar CIK %s failed: %s", cik, e)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FILING_COLS)


def holders_13f(http: Http, start: date, end: date, cusip: str = config.GME_CUSIP, pages: int = 3) -> pd.DataFrame:
    """13F-HR filings whose information table names GME's CUSIP. One row per filing; the holding size needs the XML (follow-up)."""
    rows = []
    for page in range(pages):
        params = {"q": f'"{cusip}"', "forms": "13F-HR", "dateRange": "custom", "startdt": start.isoformat(), "enddt": end.isoformat()}
        if page:
            params["from"] = page * 100
            params["page"] = page + 1
        js = http.get_json(FTS, params=params, headers=_headers(), fixture="edgar/efts_13f")
        hits = (js.get("hits") or {}).get("hits") or []
        for h in hits:
            s = h.get("_source", {})
            ciks = s.get("ciks") or [""]
            adsh = s.get("adsh", "")
            rows.append({
                "adsh": adsh, "filer": (s.get("display_names") or [""])[0].split("  (CIK")[0], "cik": ciks[0],
                "file_date": s.get("file_date"), "period_ending": s.get("period_ending"), "form": s.get("form"),
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(ciks[0])}/{adsh.replace('-', '')}/" if ciks[0] and adsh else None,
                "total_hits": ((js.get("hits") or {}).get("total") or {}).get("value"),
            })
        if len(hits) < 100 or config.fixture_mode():
            break
    df = pd.DataFrame(rows)
    if not df.empty:
        df["file_date"] = pd.to_datetime(df["file_date"]).dt.date
        df["period_ending"] = pd.to_datetime(df["period_ending"], errors="coerce").dt.date
        df = df.drop_duplicates("adsh")
    return df.reset_index(drop=True)
