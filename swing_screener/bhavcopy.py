"""Delivery % from NSE's daily sec_bhavdata_full bhavcopy.

NSE requires session cookies from the main site before archive downloads
succeed, and blocks non-browser-like requests. If a day's bhavcopy can't be
fetched, callers get back a missing value for that date -- this module never
estimates or interpolates delivery %.
"""

import logging
import os
from datetime import date
from typing import Dict, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,application/octet-stream,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/all-reports",
}

# NSE moved bhavcopy archives to this subdomain; keep the older one as a
# fallback in case a given environment resolves differently.
_URL_CANDIDATES = [
    "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv",
    "https://archives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv",
]


def _new_session(timeout: int) -> requests.Session:
    session = requests.Session()
    session.headers.update(_BASE_HEADERS)
    try:
        session.get("https://www.nseindia.com", timeout=timeout)
    except Exception as exc:
        logger.debug("NSE homepage warmup failed (continuing anyway): %s", exc)
    return session


def _cache_path(cache_dir: str, day: date) -> str:
    return os.path.join(cache_dir, f"sec_bhavdata_full_{day.strftime('%d%m%Y')}.csv")


def fetch_bhavcopy(day: date, cache_dir: str, timeout: int = 30, session: Optional[requests.Session] = None) -> Optional[pd.DataFrame]:
    """Return a DataFrame indexed by SYMBOL with a DELIV_PER column for the
    given trading date, or None if it could not be obtained. Cached to disk
    once fetched so reruns don't re-download the same day."""
    cache_path = _cache_path(cache_dir, day)
    if os.path.exists(cache_path):
        try:
            df = pd.read_csv(cache_path, index_col="SYMBOL")
            return df
        except Exception:
            pass  # fall through and refetch

    session = session or _new_session(timeout)
    ddmmyyyy = day.strftime("%d%m%Y")

    for url_template in _URL_CANDIDATES:
        url = url_template.format(ddmmyyyy=ddmmyyyy)
        try:
            resp = session.get(url, timeout=timeout)
            if resp.status_code != 200 or not resp.text.strip():
                continue
            text = resp.text
            if text.lstrip().lower().startswith("<!doctype") or text.lstrip().lower().startswith("<html"):
                continue

            from io import StringIO
            df = pd.read_csv(StringIO(text))
            df.columns = [c.strip() for c in df.columns]
            if "SYMBOL" not in df.columns or "DELIV_PER" not in df.columns:
                continue

            df["SYMBOL"] = df["SYMBOL"].astype(str).str.strip()
            if "SERIES" in df.columns:
                df = df[df["SERIES"].astype(str).str.strip() == "EQ"]
            df["DELIV_PER"] = pd.to_numeric(df["DELIV_PER"], errors="coerce")
            df = df.dropna(subset=["DELIV_PER"]).set_index("SYMBOL")[["DELIV_PER"]]
            df = df[~df.index.duplicated(keep="last")]

            df.to_csv(cache_path)
            return df
        except Exception as exc:
            logger.debug("Bhavcopy fetch failed for %s at %s: %s", day, url, exc)
            continue

    logger.warning("Could not fetch NSE bhavcopy for %s from any source", day)
    return None


def get_delivery_data(symbols, trading_dates, cache_dir: str, timeout: int = 30) -> Dict[str, Dict[str, float]]:
    """Fetch bhavcopy for every date in trading_dates once, and return
    {symbol: {'today_pct': float|None, 'avg20_pct': float|None}} where
    today_pct is delivery % on the last date and avg20_pct is the mean over
    all-but-the-last date in trading_dates (however many were available).

    A symbol not present in a given day's bhavcopy simply contributes no
    value for that day rather than failing the whole computation.
    """
    if not trading_dates:
        return {}

    trading_dates = sorted(trading_dates)
    today = trading_dates[-1]
    prior_days = trading_dates[:-1]

    session = _new_session(timeout)
    by_date: Dict[date, Optional[pd.DataFrame]] = {}
    for day in trading_dates:
        by_date[day] = fetch_bhavcopy(day, cache_dir, timeout=timeout, session=session)

    result: Dict[str, Dict[str, float]] = {}
    today_df = by_date.get(today)
    for symbol in symbols:
        today_pct = None
        if today_df is not None and symbol in today_df.index:
            today_pct = float(today_df.loc[symbol, "DELIV_PER"])

        prior_values = []
        for day in prior_days:
            df = by_date.get(day)
            if df is not None and symbol in df.index:
                prior_values.append(float(df.loc[symbol, "DELIV_PER"]))

        avg20_pct = sum(prior_values) / len(prior_values) if prior_values else None
        result[symbol] = {"today_pct": today_pct, "avg20_pct": avg20_pct}

    any_fetched = any(df is not None for df in by_date.values())
    if not any_fetched:
        logger.warning(
            "NSE bhavcopy unavailable for all %d requested dates -- delivery %% will show 'n/a' "
            "for every stock this run.", len(trading_dates)
        )
    return result
