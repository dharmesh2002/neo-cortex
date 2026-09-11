"""Confluence signal: price sits at a horizontal support level that also
coincides with the 200-day MA and the 61.8% Fibonacci retracement of the
prior 252-day range, while RSI(14) is oversold (<=35), and today's candle
is a bullish engulfing pattern.

All five conditions must be true simultaneously:
  1. Close within 2% of the nearest swing-low support (120-day rolling min).
  2. Close within 2% of the 200-day SMA.
  3. Close within 2% of the 61.8% Fibonacci retracement of the 252-day
     high-low range (H - 0.618*(H - L)).
  4. RSI(14) <= 35.
  5. Bullish engulfing: prior candle is red (close < open), today's candle
     is green (close > open), and today's body fully engulfs the prior
     body (open <= prior close AND close >= prior open).
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from .indicators import rsi

logger = logging.getLogger(__name__)

TOLERANCE_PCT = 2.0
RSI_OVERSOLD = 35.0
SMA_WINDOW = 200
RSI_PERIOD = 14
FIBO_LOOKBACK = 252
SUPPORT_LOOKBACK = 120
LIQUIDITY_THRESHOLD_INR = 20 * 1e7
MIN_HISTORY_ROWS = 220  # 200 for SMA(200) warmup + comfortable buffer


def _pct_diff(a: float, b: float) -> float:
    """Absolute % difference between two prices."""
    if b == 0:
        return float("inf")
    return abs(a - b) / b * 100


@dataclass
class ConfluenceCandidate:
    ticker: str
    close: float
    sma200: float
    fib618: float
    horizontal_support: float
    rsi14: float
    avg_daily_value_20d: float
    near_support: bool
    near_sma200: bool
    near_fib618: bool
    rsi_oversold: bool
    bullish_engulfing: bool

    @property
    def conditions_met(self) -> int:
        return sum([
            self.near_support, self.near_sma200, self.near_fib618,
            self.rsi_oversold, self.bullish_engulfing,
        ])

    @property
    def is_signal(self) -> bool:
        return self.conditions_met == 5

    @property
    def missing_conditions(self) -> List[str]:
        missing = []
        if not self.near_support:
            missing.append("Horizontal support")
        if not self.near_sma200:
            missing.append("200-day MA")
        if not self.near_fib618:
            missing.append("61.8% Fibonacci")
        if not self.rsi_oversold:
            missing.append("RSI oversold")
        if not self.bullish_engulfing:
            missing.append("Bullish engulfing")
        return missing


def evaluate_confluence_ticker(df: pd.DataFrame) -> Optional[ConfluenceCandidate]:
    df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    open_ = df["Open"]
    volume = df["Volume"]

    sma200_series = close.rolling(window=SMA_WINDOW).mean()
    rsi_series = rsi(close, period=RSI_PERIOD)
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()

    if (pd.isna(sma200_series.iloc[-1]) or pd.isna(rsi_series.iloc[-1])
            or pd.isna(avg_daily_value_20d.iloc[-1])):
        return None
    if len(df) < 2:
        return None

    close_today = float(close.iloc[-1])
    open_today = float(open_.iloc[-1])
    open_prev = float(open_.iloc[-2])
    close_prev = float(close.iloc[-2])
    rsi_today = float(rsi_series.iloc[-1])
    sma200 = float(sma200_series.iloc[-1])

    # Fibonacci: use the full available lookback up to FIBO_LOOKBACK days
    lookback = min(FIBO_LOOKBACK, len(df))
    h = float(high.iloc[-lookback:].max())
    l_val = float(low.iloc[-lookback:].min())
    fib618 = h - 0.618 * (h - l_val) if h != l_val else close_today

    # Horizontal support: rolling min of lows over SUPPORT_LOOKBACK days
    support_lookback = min(SUPPORT_LOOKBACK, len(df))
    horizontal_support = float(low.iloc[-support_lookback:].min())

    liquidity_ok = bool(avg_daily_value_20d.iloc[-1] >= LIQUIDITY_THRESHOLD_INR)

    near_support = bool(_pct_diff(close_today, horizontal_support) <= TOLERANCE_PCT)
    near_sma200 = bool(_pct_diff(close_today, sma200) <= TOLERANCE_PCT)
    near_fib618 = bool(_pct_diff(close_today, fib618) <= TOLERANCE_PCT)
    rsi_oversold = bool(rsi_today <= RSI_OVERSOLD)

    # Bullish engulfing: prior candle is red, today is green, today's body
    # fully covers the prior body.
    prior_red = close_prev < open_prev
    today_green = close_today > open_today
    body_engulfs = open_today <= close_prev and close_today >= open_prev
    bullish_engulfing = bool(prior_red and today_green and body_engulfs)

    return ConfluenceCandidate(
        ticker="",
        close=close_today,
        sma200=sma200,
        fib618=fib618,
        horizontal_support=horizontal_support,
        rsi14=rsi_today,
        avg_daily_value_20d=float(avg_daily_value_20d.iloc[-1]),
        near_support=near_support,
        near_sma200=near_sma200,
        near_fib618=near_fib618,
        rsi_oversold=rsi_oversold,
        bullish_engulfing=bullish_engulfing,
    )


def run_confluence_signal_screen(csv_dir: str = None,
                                  info_sleep_seconds: float = 0.3) -> Dict:
    import time
    import yfinance as yf

    from .screener import fetch_price_history
    from .universe import build_universe, is_excluded

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(
        zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"]))
    )

    history = fetch_price_history(tickers, period="18mo")
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    signals: List[dict] = []
    near_miss: List[dict] = []

    for ticker, df in history.items():
        result = evaluate_confluence_ticker(df)
        if result is None:
            continue
        result.ticker = ticker

        if not (result.conditions_met >= 4 or result.is_signal):
            continue

        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as exc:
            logger.warning("Could not fetch sector/industry for %s: %s", ticker, exc)
            info = {}
        if info_sleep_seconds:
            time.sleep(info_sleep_seconds)

        sector = info.get("sector", "")
        industry = info.get("industry", "")
        if is_excluded(sector, industry):
            continue

        row = {
            "ticker": ticker,
            "company": ticker_to_company.get(ticker, ticker),
            "sector": sector,
            "industry": industry,
            "close": result.close,
            "sma200": result.sma200,
            "fib618": result.fib618,
            "horizontal_support": result.horizontal_support,
            "rsi14": result.rsi14,
            "avg_daily_value_cr": result.avg_daily_value_20d / 1e7,
            "near_support": result.near_support,
            "near_sma200": result.near_sma200,
            "near_fib618": result.near_fib618,
            "rsi_oversold": result.rsi_oversold,
            "bullish_engulfing": result.bullish_engulfing,
            "conditions_met": result.conditions_met,
        }

        if result.is_signal:
            signals.append(row)
        else:
            row["missing"] = ", ".join(result.missing_conditions)
            near_miss.append(row)

    return {
        "signals": signals,
        "near_miss": near_miss,
        "universe_size": len(tickers),
        "history_fetched": len(history),
    }
