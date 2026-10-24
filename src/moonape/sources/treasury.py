"""US Treasury daily par yield curve (keyless, same-day close around 4pm ET)."""
from __future__ import annotations

import io

import pandas as pd

from moonape.http import Http

URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all"
       "?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv")
TENORS = {"1 Mo": "1M", "1.5 Month": "1.5M", "2 Mo": "2M", "3 Mo": "3M", "4 Mo": "4M", "6 Mo": "6M", "1 Yr": "1Y", "2 Yr": "2Y",
          "3 Yr": "3Y", "5 Yr": "5Y", "7 Yr": "7Y", "10 Yr": "10Y", "20 Yr": "20Y", "30 Yr": "30Y"}
TENOR_MONTHS = {"1M": 1, "1.5M": 1.5, "2M": 2, "3M": 3, "4M": 4, "6M": 6, "1Y": 12, "2Y": 24, "3Y": 36, "5Y": 60, "7Y": 84, "10Y": 120, "20Y": 240, "30Y": 360}


def fetch_year(http: Http, year: int) -> pd.DataFrame:
    """Long table: date, tenor, months, yield (percent)."""
    r = http.get(URL.format(year=year), fixture=f"treasury/{year}")
    wide = pd.read_csv(io.StringIO(r.text))
    wide["Date"] = pd.to_datetime(wide["Date"], format="%m/%d/%Y").dt.date
    cols = [c for c in wide.columns if c in TENORS]
    long = wide.melt(id_vars="Date", value_vars=cols, var_name="tenor", value_name="yield")
    long["tenor"] = long["tenor"].map(TENORS)
    long["months"] = long["tenor"].map(TENOR_MONTHS)
    long["yield"] = pd.to_numeric(long["yield"], errors="coerce")
    return long.rename(columns={"Date": "date"}).dropna(subset=["yield"]).sort_values(["date", "months"]).reset_index(drop=True)
