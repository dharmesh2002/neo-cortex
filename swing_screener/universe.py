"""Universe construction: Nifty 50 + Nifty Next 50 + Nifty Midcap 50 (150
stocks), freshly pulled from niftyindices.com on every run. Constituent
lists are reshuffled periodically, so a cached/bundled copy would silently
go stale -- this module never reuses an old list.
"""

import io
import logging
import time

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# niftyindices.com sits behind bot protection that rejects requests without a
# browser-like User-Agent and appears to rate-limit back-to-back requests.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
    "Referer": "https://niftyindices.com/",
}

_REQUEST_SPACING_SECONDS = 3.0


def _find_header_index(lines) -> int:
    """Locate the real header row: the first line whose comma-split fields
    contain an exact (case-insensitive) "Symbol" token."""
    for i, line in enumerate(lines):
        fields = [f.strip().strip('"').strip("﻿") for f in line.split(",")]
        if any(f.lower() == "symbol" for f in fields):
            return i
    return 0


def _fetch_csv(name: str, url: str, timeout: int) -> pd.DataFrame:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    text = resp.text

    stripped_lower = text.lstrip().lower()
    if stripped_lower.startswith("<!doctype html") or stripped_lower.startswith("<html"):
        raise ValueError(
            f"{name}: niftyindices.com returned an HTML page instead of a CSV "
            f"(likely bot-protection/rate-limiting) for {url}"
        )

    lines = text.splitlines()
    header_idx = _find_header_index(lines)
    cleaned = "\n".join(lines[header_idx:])

    df = pd.read_csv(io.StringIO(cleaned), engine="python", on_bad_lines="skip")
    df.columns = [c.strip().strip("﻿") for c in df.columns]

    rename_map = {c: "Symbol" for c in df.columns if c.lower() == "symbol"}
    df = df.rename(columns=rename_map)
    if "Symbol" not in df.columns:
        raise ValueError(
            f"No Symbol column found for {name}; got columns {list(df.columns)}"
        )

    industry_col = next((c for c in df.columns if c.lower() == "industry"), None)
    if industry_col and industry_col != "Industry":
        df = df.rename(columns={industry_col: "Industry"})
    if "Industry" not in df.columns:
        df["Industry"] = ""

    company_col = next((c for c in df.columns if c.lower() in ("company name", "companyname")), None)
    if company_col and company_col != "Company Name":
        df = df.rename(columns={company_col: "Company Name"})
    if "Company Name" not in df.columns:
        df["Company Name"] = df["Symbol"]

    df = df.dropna(subset=["Symbol"])
    df["Index"] = name
    return df[["Symbol", "Company Name", "Industry", "Index"]]


def _fetch_with_retries(name: str, url: str, retries: int, backoff: float, timeout: int) -> pd.DataFrame:
    last_err = None
    for attempt in range(retries):
        try:
            return _fetch_csv(name, url, timeout)
        except Exception as exc:  # network hiccups, transient 403s, etc.
            last_err = exc
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    raise RuntimeError(
        f"Failed to fetch {name} constituent list from {url} after {retries} attempts: {last_err}"
    )


def build_universe(config) -> pd.DataFrame:
    """Return a DataFrame of the current Nifty 50 + Next 50 + Midcap 50
    universe (150 names, duplicates dropped) with columns Symbol, Ticker,
    Company Name, Industry, Index. Always fetched fresh from niftyindices.com.
    """
    urls = config.niftyindices_urls
    retries = config.get("request_retries", 3)
    backoff = config.get("request_backoff_seconds", 5.0)
    timeout = config.get("request_timeout_seconds", 45)

    frames = []
    for i, (name, url) in enumerate(urls.items()):
        if i > 0:
            time.sleep(_REQUEST_SPACING_SECONDS)
        df = _fetch_with_retries(name, url, retries, backoff, timeout)
        frames.append(df)
        logger.info("Fetched %d constituents for %s", len(df), name)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["Symbol"], keep="first")
    combined["Symbol"] = combined["Symbol"].str.strip()
    combined["Ticker"] = combined["Symbol"] + ".NS"
    combined["Industry"] = combined["Industry"].fillna("").astype(str).str.strip()
    return combined.reset_index(drop=True)


def is_excluded(industry: str, config) -> bool:
    """Standing exclusion: drop Technology/IT and Energy sectors, and any
    Airlines/Oil/Gas/Petroleum/Chemicals/Paint industry, regardless of signal."""
    industry_l = (industry or "").strip().lower()
    sector_keywords = config.get("excluded_sector_keywords", [])
    industry_keywords = config.get("excluded_industry_keywords", [])
    if any(kw in industry_l for kw in sector_keywords):
        return True
    return any(kw in industry_l for kw in industry_keywords)


def map_sector_index(industry: str, config) -> str:
    """Map an Industry string to an NSE sector-index yfinance ticker via
    keyword substring match; 'n/a' if nothing matches."""
    industry_l = (industry or "").strip().lower()
    for keyword, index_ticker in config.sector_index_map.items():
        if keyword in industry_l:
            return index_ticker
    return "n/a"
