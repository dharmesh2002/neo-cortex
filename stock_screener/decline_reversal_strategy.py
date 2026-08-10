"""Screens for a multi-day decline followed by today's green reversal
candle, occurring near a real support level.

"Daily candle failing from the last few days" is read as: the prior 3
trading days each closed lower than the day before -- a genuine losing
streak, not just noisy chop. "Now a green candle is created" is read as:
today's candle closes above its own open (a green/bullish candle) AND above
yesterday's close (an actual reversal, not just a smaller red candle).
"Having support here" reuses the same support-level methodology as the
ad-hoc support/resistance lookup (moving averages + recent swing lows +
the Bollinger lower band, whichever of those sits highest below today's
close) -- today's close must land within 2% of that nearest support level.

Pure price-action pattern detection, no fundamentals filter -- only this
project's standing liquidity and sector/industry exclusion rules apply.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from .indicators import bollinger_bands

logger = logging.getLogger(__name__)

DECLINE_STREAK_DAYS = 3
SUPPORT_TOLERANCE_PCT = 2.0  # today's close must be within this many % of the nearest support level
LIQUIDITY_THRESHOLD_INR = 20 * 1e7
SMA_WINDOWS = (20, 50, 100, 200)
SWING_LOW_WINDOWS = (20, 60, 120, 252)
BB_WINDOW = 20
BACKTEST_PERIOD = "2y"
MIN_HISTORY_ROWS = 260  # need a full year+ for the 252-day swing low / 200-day SMA


@dataclass
class DeclineReversalCandidate:
    ticker: str
    close: float
    open_: float
    prev_close: float
    nearest_support: float
    pct_above_support: float
    decline_streak_days: int
    avg_daily_value_20d: float


def evaluate_ticker(df: pd.DataFrame) -> Optional[DeclineReversalCandidate]:
    df = df.dropna(subset=["Close", "Open", "High", "Low", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close, open_, low, volume = df["Close"], df["Open"], df["Low"], df["Volume"]
    n = len(df)
    if n < DECLINE_STREAK_DAYS + 2:
        return None

    # The DECLINE_STREAK_DAYS days right before today must each have closed
    # lower than the day before it -- a genuine losing streak, not chop.
    for i in range(1, DECLINE_STREAK_DAYS + 1):
        if not (close.iloc[-1 - i] < close.iloc[-2 - i]):
            return None

    close_today = float(close.iloc[-1])
    open_today = float(open_.iloc[-1])
    close_prev = float(close.iloc[-2])

    is_green = close_today > open_today
    is_reversal = close_today > close_prev
    if not (is_green and is_reversal):
        return None

    avg_daily_value_20d = (close * volume).rolling(window=20).mean().iloc[-1]
    if pd.isna(avg_daily_value_20d) or avg_daily_value_20d < LIQUIDITY_THRESHOLD_INR:
        return None

    levels = []
    for window in SMA_WINDOWS:
        if len(close) >= window:
            v = float(close.rolling(window=window).mean().iloc[-1])
            if pd.notna(v):
                levels.append(v)
    for window in SWING_LOW_WINDOWS:
        if len(low) >= window:
            levels.append(float(low.iloc[-window:].min()))
    _, _, bb_lower = bollinger_bands(close, window=BB_WINDOW)
    if pd.notna(bb_lower.iloc[-1]):
        levels.append(float(bb_lower.iloc[-1]))

    below = [lvl for lvl in levels if lvl < close_today]
    if not below:
        return None
    nearest_support = max(below)
    pct_above_support = (close_today - nearest_support) / nearest_support * 100

    if pct_above_support > SUPPORT_TOLERANCE_PCT:
        return None

    return DeclineReversalCandidate(
        ticker="",
        close=close_today,
        open_=open_today,
        prev_close=close_prev,
        nearest_support=nearest_support,
        pct_above_support=pct_above_support,
        decline_streak_days=DECLINE_STREAK_DAYS,
        avg_daily_value_20d=float(avg_daily_value_20d),
    )


def run_decline_reversal_screen(csv_dir: str = None, info_sleep_seconds: float = 0.3) -> Dict:
    from .screener import fetch_price_history, fetch_sector_industry
    from .universe import build_universe, is_excluded

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers, period=BACKTEST_PERIOD)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    matches: List[dict] = []
    for ticker, df in history.items():
        cand = evaluate_ticker(df)
        if cand is None:
            continue
        cand.ticker = ticker

        sector_info = fetch_sector_industry(ticker, info_sleep_seconds)
        if is_excluded(sector_info["sector"], sector_info["industry"]):
            continue

        matches.append({
            "ticker": ticker,
            "company": ticker_to_company.get(ticker, ticker),
            "sector": sector_info["sector"],
            "industry": sector_info["industry"],
            "close": cand.close,
            "open": cand.open_,
            "prev_close": cand.prev_close,
            "nearest_support": cand.nearest_support,
            "pct_above_support": cand.pct_above_support,
            "decline_streak_days": cand.decline_streak_days,
            "avg_daily_value_cr": cand.avg_daily_value_20d / 1e7,
        })

    matches.sort(key=lambda r: r["pct_above_support"])

    return {
        "matches": matches,
        "universe_size": len(tickers),
        "history_fetched": len(history),
    }
