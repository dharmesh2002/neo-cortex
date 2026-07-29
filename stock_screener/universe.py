"""Universe construction: Nifty 50 + Nifty Next 50 + Nifty Midcap 50, freshly
pulled from niftyindices.com every run (the constituent lists are reshuffled
roughly every six months, so a cached/bundled copy would silently go stale).
"""

import io
import logging
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

INDEX_URLS = {
    "NIFTY50": "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
    "NIFTYNEXT50": "https://niftyindices.com/IndexConstituent/ind_niftynext50list.csv",
    "NIFTYMIDCAP50": "https://niftyindices.com/IndexConstituent/ind_nifty_midcap50list.csv",
}

# niftyindices.com sits behind bot protection that rejects requests without a
# browser-like User-Agent, and appears to rate-limit/challenge back-to-back
# requests -- hitting all 3 index URLs with no delay got an HTML block page
# back (200 OK, body starting "<!DOCTYPE html>") instead of the 3rd CSV.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
    "Referer": "https://niftyindices.com/",
}

# Minimum gap between successive requests to niftyindices.com.
_REQUEST_SPACING_SECONDS = 3.0

# yfinance sector/industry taxonomy keywords for the standing exclusion list.
EXCLUDED_SECTORS = {"technology", "energy"}
EXCLUDED_INDUSTRY_KEYWORDS = ("airlin", "oil", "gas", "petroleum", "chemical", "paint")


def _find_header_index(lines) -> int:
    """Locate the real header row: the first line whose comma-split fields
    contain an exact (case-insensitive) "Symbol" token, not just a line that
    happens to mention the word in a preamble/disclaimer sentence."""
    for i, line in enumerate(lines):
        fields = [f.strip().strip('"').strip("﻿") for f in line.split(",")]
        if any(f.lower() == "symbol" for f in fields):
            return i
    return 0


def _fetch_csv(name: str, url: str, timeout: int = 20) -> pd.DataFrame:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    text = resp.text

    stripped_lower = text.lstrip().lower()
    if stripped_lower.startswith("<!doctype html") or stripped_lower.startswith("<html"):
        raise ValueError(
            f"{name}: niftyindices.com returned an HTML page instead of a CSV "
            f"(likely bot-protection/rate-limiting) for {url}"
        )

    # niftyindices.com CSVs occasionally carry a stray preamble line before
    # the real header, and a rogue unescaped comma in a company name here or
    # there -- skip to the header row and tolerate ragged data rows rather
    # than letting one bad line blow up the whole fetch.
    lines = text.splitlines()
    header_idx = _find_header_index(lines)
    cleaned = "\n".join(lines[header_idx:])

    df = pd.read_csv(io.StringIO(cleaned), engine="python", on_bad_lines="skip")
    df.columns = [c.strip().strip("﻿") for c in df.columns]

    rename_map = {c: "Symbol" for c in df.columns if c.lower() == "symbol"}
    df = df.rename(columns=rename_map)
    if "Symbol" not in df.columns:
        raise ValueError(
            f"No Symbol column found for {name}; got columns {list(df.columns)} "
            f"(header row detected at line {header_idx}: {lines[header_idx]!r})"
        )

    df = df.dropna(subset=["Symbol"])
    df["Index"] = name
    return df


def _fetch_with_retries(name: str, url: str, retries: int, backoff: float) -> pd.DataFrame:
    last_err = None
    for attempt in range(retries):
        try:
            return _fetch_csv(name, url)
        except Exception as exc:  # network hiccups, transient 403s, etc.
            last_err = exc
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {name} constituent list from {url}: {last_err}")


def build_universe(csv_dir: str = None, retries: int = 4, backoff: float = 4.0) -> pd.DataFrame:
    """Return a DataFrame of the current 150-stock universe with a Ticker column.

    By default fetches fresh CSVs from niftyindices.com. If that site is
    unreachable from this environment, pass csv_dir pointing at a directory
    containing freshly (same-day) downloaded copies named
    ind_nifty50list.csv, ind_niftynext50list.csv, ind_nifty_midcap50list.csv
    -- never reuse an old export, since these lists change every 6 months.
    """
    frames = []
    for i, (name, url) in enumerate(INDEX_URLS.items()):
        if csv_dir:
            filename = url.rsplit("/", 1)[-1]
            path = f"{csv_dir.rstrip('/')}/{filename}"
            df = pd.read_csv(path)
            df.columns = [c.strip() for c in df.columns]
            df["Index"] = name
        else:
            if i > 0:
                time.sleep(_REQUEST_SPACING_SECONDS)
            df = _fetch_with_retries(name, url, retries, backoff)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["Symbol"], keep="first")
    combined["Ticker"] = combined["Symbol"].str.strip() + ".NS"
    return combined.reset_index(drop=True)


def is_excluded(sector: str, industry: str) -> bool:
    """Standing preference: drop Technology/Energy sector names and any
    Airlines/Oil/Gas/Petroleum/Chemicals/Paint industry, regardless of signal.
    """
    sector_l = (sector or "").strip().lower()
    industry_l = (industry or "").strip().lower()
    if sector_l in EXCLUDED_SECTORS:
        return True
    return any(keyword in industry_l for keyword in EXCLUDED_INDUSTRY_KEYWORDS)
