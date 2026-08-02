"""Detects a recent gap-down that hasn't been filled yet -- the classic
technical pattern where a stock opens well below the prior day's close
(often on news/results) and price often, not always, eventually trades back
up to close that gap. Pure price-history detection; no fundamentals.
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

GAP_THRESHOLD_PCT = 2.0  # minimum gap-down size to count, in %
LOOKBACK_DAYS = 60  # how far back to look for the most recent qualifying gap
LIQUIDITY_THRESHOLD_INR = 20 * 1e7  # 20 crore, same liquidity bar used elsewhere
MIN_HISTORY_ROWS = 65


@dataclass
class GapCandidate:
    ticker: str
    close: float
    days_since_gap: int
    pre_gap_close: float
    gap_pct: float
    pct_to_fill: float
    avg_daily_value_20d: float


def find_unfilled_gap(df: pd.DataFrame, lookback_days: int = LOOKBACK_DAYS) -> Optional[GapCandidate]:
    """Scans backward from today for the most recent gap-down day (today's
    Open at least GAP_THRESHOLD_PCT below yesterday's Close) and reports it
    only if price hasn't since closed back up to that pre-gap level."""
    df = df.dropna(subset=["Close", "Open", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close, open_, volume = df["Close"], df["Open"], df["Volume"]
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()
    if pd.isna(avg_daily_value_20d.iloc[-1]) or avg_daily_value_20d.iloc[-1] < LIQUIDITY_THRESHOLD_INR:
        return None

    current_close = float(close.iloc[-1])
    n = len(df)
    earliest_index = max(1, n - lookback_days)

    for i in range(n - 1, earliest_index - 1, -1):
        prev_close = float(close.iloc[i - 1])
        today_open = float(open_.iloc[i])
        if prev_close <= 0:
            continue
        gap_pct = (today_open - prev_close) / prev_close * 100

        if gap_pct <= -GAP_THRESHOLD_PCT:
            # Most recent qualifying gap found. Only a signal if still unfilled;
            # if it's already filled, don't keep searching for an older one --
            # price has since recovered past this point, so an older gap
            # further back is very likely filled too.
            if current_close < prev_close:
                return GapCandidate(
                    ticker="",
                    close=current_close,
                    days_since_gap=(n - 1) - i,
                    pre_gap_close=prev_close,
                    gap_pct=gap_pct,
                    pct_to_fill=(prev_close - current_close) / current_close * 100,
                    avg_daily_value_20d=float(avg_daily_value_20d.iloc[-1]),
                )
            return None
    return None


def run_gap_fill_screen(csv_dir: str = None, info_sleep_seconds: float = 0.3) -> Dict:
    from .screener import fetch_price_history
    from .universe import build_universe, is_excluded

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    matches: List[dict] = []
    for ticker, df in history.items():
        cand = find_unfilled_gap(df)
        if cand is None:
            continue
        cand.ticker = ticker

        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as exc:
            logger.warning("Could not fetch sector/industry for %s: %s", ticker, exc)
            info = {}
        time.sleep(info_sleep_seconds)

        sector = info.get("sector", "")
        industry = info.get("industry", "")
        if is_excluded(sector, industry):
            continue

        matches.append({
            "ticker": ticker,
            "company": ticker_to_company.get(ticker, ticker),
            "sector": sector,
            "industry": industry,
            "close": cand.close,
            "gap_pct": cand.gap_pct,
            "pre_gap_close": cand.pre_gap_close,
            "pct_to_fill": cand.pct_to_fill,
            "days_since_gap": cand.days_since_gap,
            "avg_daily_value_cr": cand.avg_daily_value_20d / 1e7,
        })

    # Most recent gaps first -- a gap from 2 days ago is more actionable
    # context than one from 55 days ago that just hasn't fully closed.
    matches.sort(key=lambda r: r["days_since_gap"])

    return {
        "matches": matches,
        "universe_size": len(tickers),
        "history_fetched": len(history),
    }
