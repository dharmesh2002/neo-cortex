"""Ad-hoc support/resistance level lookup for an explicit ticker list.
Computes moving averages (which act as dynamic support/resistance) and
recent swing lows (static price floors from actual price history) --
the standard, verifiable way to identify support levels, rather than an
eyeballed guess.
"""

import logging
from typing import Dict, List

import pandas as pd
import yfinance as yf

from .indicators import bollinger_bands

logger = logging.getLogger(__name__)

SMA_WINDOWS = (20, 50, 100, 200)
SWING_LOW_WINDOWS = (20, 60, 120, 252)  # ~1mo, ~3mo, ~6mo, ~1yr of trading days


def compute_support_levels(ticker: str, period: str = "2y") -> Dict:
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=False, progress=False)
    if df is None or df.empty:
        return {"ticker": ticker, "error": "no data returned"}

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["Close", "Low"])
    close, low = df["Close"], df["Low"]
    if len(close) < 25:
        return {"ticker": ticker, "error": "not enough history"}

    close_today = float(close.iloc[-1])

    smas = {}
    for window in SMA_WINDOWS:
        if len(close) >= window:
            smas[f"sma_{window}"] = float(close.rolling(window=window).mean().iloc[-1])
        else:
            smas[f"sma_{window}"] = None

    swing_lows = {}
    for window in SWING_LOW_WINDOWS:
        if len(low) >= window:
            swing_lows[f"low_{window}d"] = float(low.iloc[-window:].min())
        else:
            swing_lows[f"low_{window}d"] = None

    _, _, bb_lower = bollinger_bands(close, window=20)
    bb_lower_today = float(bb_lower.iloc[-1]) if not pd.isna(bb_lower.iloc[-1]) else None

    week_52_low = float(low.iloc[-252:].min()) if len(low) >= 20 else float(low.min())
    week_52_high = float(df["High"].iloc[-252:].max()) if len(df["High"]) >= 20 else float(df["High"].max())

    return {
        "ticker": ticker,
        "close": close_today,
        "bollinger_lower": bb_lower_today,
        **smas,
        **swing_lows,
        "week_52_low": week_52_low,
        "week_52_high": week_52_high,
    }


def check_support_levels_for_tickers(tickers: List[str], period: str = "2y") -> List[dict]:
    return [compute_support_levels(t, period=period) for t in tickers]
