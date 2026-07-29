"""Technical indicator calculations shared by the screener."""

import numpy as np
import pandas as pd


def bollinger_bands(close: pd.Series, window: int = 20, num_std: float = 2.0):
    """20-day SMA and the +/- num_std standard deviation bands."""
    sma = close.rolling(window=window).mean()
    std = close.rolling(window=window).std(ddof=0)
    upper = sma + num_std * std
    lower = sma - num_std * std
    return sma, upper, lower


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's RSI."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_values = 100 - (100 / (1 + rs))
    return rsi_values.where(avg_loss != 0, 100.0)


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's Average True Range."""
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
