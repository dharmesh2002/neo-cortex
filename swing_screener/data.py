"""Price-history fetching with local caching. Fetches full history once,
then only pulls missing days on reruns. Also checks the latest cached
candle is today's date so the screener never runs on stale data.
"""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from typing import Dict, Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def _cache_path(cache_dir: str, ticker: str) -> str:
    safe_name = ticker.replace("^", "_INDEX_")
    return os.path.join(cache_dir, f"{safe_name}.csv")


def _load_cache(cache_dir: str, ticker: str) -> Optional[pd.DataFrame]:
    path = _cache_path(cache_dir, ticker)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        if df.empty:
            return None
        return df[_REQUIRED_COLUMNS]
    except Exception as exc:
        logger.warning("Could not read cache for %s (%s); refetching fully", ticker, exc)
        return None


def _save_cache(cache_dir: str, ticker: str, df: pd.DataFrame) -> None:
    path = _cache_path(cache_dir, ticker)
    df[_REQUIRED_COLUMNS].to_csv(path)


def _download(ticker: str, start: Optional[str], period: Optional[str], timeout: int) -> pd.DataFrame:
    kwargs = dict(interval="1d", auto_adjust=False, progress=False, threads=False, timeout=timeout)
    if start:
        df = yf.download(ticker, start=start, **kwargs)
    else:
        df = yf.download(ticker, period=period, **kwargs)
    if df is None or df.empty:
        return pd.DataFrame(columns=_REQUIRED_COLUMNS)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[_REQUIRED_COLUMNS]


def fetch_one(ticker: str, config) -> pd.DataFrame:
    """Return the full cached-plus-fresh OHLCV history for one ticker,
    fetching only the days missing since the last cached candle."""
    cache_dir = config.cache_dir
    cached = _load_cache(cache_dir, ticker)
    timeout = config.get("request_timeout_seconds", 45)

    if cached is not None and not cached.empty:
        last_date = cached.index.max()
        start = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        if start > date.today().strftime("%Y-%m-%d"):
            fresh = pd.DataFrame(columns=_REQUIRED_COLUMNS)
        else:
            fresh = _download(ticker, start=start, period=None, timeout=timeout)
        combined = pd.concat([cached, fresh])
        combined = combined[~combined.index.duplicated(keep="last")].sort_index()
    else:
        combined = _download(ticker, start=None, period=config.history_period, timeout=timeout)

    if not combined.empty:
        _save_cache(cache_dir, ticker, combined)
    return combined


def fetch_many(tickers, config, max_workers: int = None) -> Dict[str, pd.DataFrame]:
    """Fetch (cache-aware) history for many tickers in parallel."""
    max_workers = max_workers or config.get("max_download_workers", 8)
    results: Dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_one, t, config): t for t in tickers}
        for fut in as_completed(futures):
            ticker = futures[fut]
            try:
                df = fut.result()
                if df is not None and not df.dropna(how="all").empty:
                    results[ticker] = df
                else:
                    logger.warning("No data returned for %s", ticker)
            except Exception as exc:
                logger.warning("Failed to fetch %s: %s", ticker, exc)
    return results


def latest_trading_date(history: Dict[str, pd.DataFrame]) -> Optional[pd.Timestamp]:
    """The most common latest date across all fetched series -- used as the
    reference 'today' when checking staleness (robust to one or two tickers
    lagging behind everyone else)."""
    last_dates = [df.index.max() for df in history.values() if not df.empty]
    if not last_dates:
        return None
    return max(set(last_dates), key=last_dates.count)


def is_stale(latest: Optional[pd.Timestamp], today: Optional[date] = None) -> bool:
    """True if the latest available candle is not from today (IST calendar
    date). Weekends/holidays are the caller's problem to reason about --
    this just checks 'is the data as fresh as right now'."""
    today = today or datetime.now().date()
    if latest is None:
        return True
    return latest.date() != today
