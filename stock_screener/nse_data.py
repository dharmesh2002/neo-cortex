"""Direct NSE data feeds: daily bhavcopy with delivery data, and the
Nifty 500 constituent list.

Yahoo Finance has no delivery quantity / delivery % at all, so the
resilience-accumulation strategy pulls it straight from NSE's public
archive (`sec_bhavdata_full_DDMMYYYY.csv`: OHLC, total traded quantity,
turnover, delivery quantity and delivery % for every listed security,
one file per trading day).

Each day's file is immutable once published, so it is cached on disk and
only missing days are ever downloaded.
"""

import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

BHAVCOPY_URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
NIFTY500_URL = "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv"
DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "neo_cortex_nse")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
}

NUMERIC_COLS = ["CLOSE_PRICE", "TTL_TRD_QNTY", "TURNOVER_LACS", "DELIV_QTY", "DELIV_PER"]


def _parse_bhavcopy(text: str) -> Optional[pd.DataFrame]:
    """NSE answers a holiday/weekend/not-yet-published date with an HTML
    page (not a 404), so validate the header rather than trust the status."""
    if not text.lstrip().upper().startswith("SYMBOL"):
        return None
    df = pd.read_csv(io.StringIO(text), skipinitialspace=True)
    df.columns = [c.strip() for c in df.columns]
    df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
    df["SERIES"] = df["SERIES"].astype(str).str.strip()
    df = df[df["SERIES"] == "EQ"].copy()
    for col in NUMERIC_COLS:
        # Un-deliverable rows carry "-" instead of a number.
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["SYMBOL", *NUMERIC_COLS]]


def _fetch_day(day: date, cache_dir: str) -> Optional[pd.DataFrame]:
    cache_path = os.path.join(cache_dir, f"bhav_{day.isoformat()}.csv")
    if os.path.exists(cache_path):
        return pd.read_csv(cache_path)

    url = BHAVCOPY_URL.format(ddmmyyyy=day.strftime("%d%m%Y"))
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=45)
    except requests.RequestException as exc:
        logger.warning("Bhavcopy %s: request failed (%s)", day, exc)
        return None
    if resp.status_code != 200:
        return None
    df = _parse_bhavcopy(resp.text)
    if df is None or df.empty:
        return None
    df.to_csv(cache_path, index=False)
    return df


def fetch_delivery_history(trading_days: int = 66, cache_dir: str = DEFAULT_CACHE_DIR,
                           end: Optional[date] = None, max_workers: int = 6) -> pd.DataFrame:
    """Return a long DataFrame (Date, SYMBOL, CLOSE_PRICE, TTL_TRD_QNTY,
    TURNOVER_LACS, DELIV_QTY, DELIV_PER) covering the most recent
    `trading_days` sessions that NSE has published.

    Weekdays only are requested; weekday holidays simply come back empty.
    """
    os.makedirs(cache_dir, exist_ok=True)
    end = end or date.today()
    # ~1.6 calendar days per trading day plus slack for holiday clusters.
    start = end - timedelta(days=int(trading_days * 1.6) + 10)
    days: List[date] = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    days = [d for d in days if d.weekday() < 5]

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(lambda d: _fetch_day(d, cache_dir), days))

    frames = []
    for day, df in zip(days, results):
        if df is not None:
            df = df.copy()
            df.insert(0, "Date", pd.Timestamp(day))
            frames.append(df)
    if not frames:
        raise RuntimeError("No NSE bhavcopy files could be downloaded -- is nsearchives.nseindia.com reachable?")

    combined = pd.concat(frames, ignore_index=True)
    keep = sorted(combined["Date"].unique())[-trading_days:]
    combined = combined[combined["Date"].isin(keep)]
    logger.info("Delivery history: %d sessions, %s -> %s",
                len(keep), pd.Timestamp(keep[0]).date(), pd.Timestamp(keep[-1]).date())
    return combined.reset_index(drop=True)


def delivery_series_by_symbol(history: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    return {sym: g.sort_values("Date").set_index("Date") for sym, g in history.groupby("SYMBOL")}


def fetch_nifty500(timeout: int = 45) -> pd.DataFrame:
    """Nifty 500 constituents (Company Name, Industry, Symbol, ...) plus a
    Ticker column in Yahoo format."""
    resp = requests.get(NIFTY500_URL, headers={**_HEADERS, "Referer": "https://niftyindices.com/"},
                        timeout=timeout)
    resp.raise_for_status()
    if resp.text.lstrip().lower().startswith(("<!doctype", "<html")):
        raise ValueError("niftyindices.com returned an HTML block page instead of the Nifty 500 CSV")
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip() for c in df.columns]
    df = df.dropna(subset=["Symbol"])
    df["Symbol"] = df["Symbol"].str.strip()
    df["Ticker"] = df["Symbol"] + ".NS"
    return df.drop_duplicates(subset=["Symbol"]).reset_index(drop=True)
