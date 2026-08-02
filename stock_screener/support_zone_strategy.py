"""Plain technical scan, no fundamentals, no extra embellishment: RSI(14)
daily sitting between 30-45, and close between the Bollinger lower and
middle band -- i.e. resting in the lower half of the channel without being
extremely oversold. Only the standing liquidity/sector-exclusion rules used
across the rest of this tool are applied; nothing else is layered on top.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from .indicators import bollinger_bands, rsi

logger = logging.getLogger(__name__)

RSI_MIN = 30.0
RSI_MAX = 45.0
BB_WINDOW = 20
RSI_PERIOD = 14
LIQUIDITY_THRESHOLD_INR = 20 * 1e7  # 20 crore, same liquidity bar used elsewhere
MIN_HISTORY_ROWS = 40


@dataclass
class SupportZoneCandidate:
    ticker: str
    close: float
    lower_band: float
    mid_band: float
    upper_band: float
    rsi14: float
    avg_daily_value_20d: float
    rsi_in_range: bool
    in_bb_zone: bool
    liquidity_ok: bool

    @property
    def matches(self) -> bool:
        return self.rsi_in_range and self.in_bb_zone and self.liquidity_ok


def evaluate_support_zone_ticker(df: pd.DataFrame) -> Optional[SupportZoneCandidate]:
    df = df.dropna(subset=["Close", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close, volume = df["Close"], df["Volume"]
    mid, upper, lower = bollinger_bands(close, window=BB_WINDOW)
    rsi_series = rsi(close, period=RSI_PERIOD)
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()

    if pd.isna(mid.iloc[-1]) or pd.isna(lower.iloc[-1]) or pd.isna(rsi_series.iloc[-1]):
        return None

    close_today = float(close.iloc[-1])
    rsi_today = float(rsi_series.iloc[-1])
    lower_today = float(lower.iloc[-1])
    mid_today = float(mid.iloc[-1])

    rsi_in_range = bool(RSI_MIN <= rsi_today <= RSI_MAX)
    in_bb_zone = bool(lower_today < close_today < mid_today)
    liquidity_ok = bool(avg_daily_value_20d.iloc[-1] >= LIQUIDITY_THRESHOLD_INR)

    return SupportZoneCandidate(
        ticker="",
        close=close_today,
        lower_band=lower_today,
        mid_band=mid_today,
        upper_band=float(upper.iloc[-1]),
        rsi14=rsi_today,
        avg_daily_value_20d=float(avg_daily_value_20d.iloc[-1]),
        rsi_in_range=rsi_in_range,
        in_bb_zone=in_bb_zone,
        liquidity_ok=liquidity_ok,
    )


def run_support_zone_screen(csv_dir: str = None) -> Dict:
    from .screener import fetch_price_history
    from .universe import build_universe, is_excluded

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    # Sector/industry is only needed to apply the standing exclusion list, and
    # only for tickers that already match on price/RSI -- avoids unnecessary
    # slow yfinance .info calls for names that wouldn't qualify anyway.
    import time
    import yfinance as yf

    matches: List[dict] = []
    for ticker, df in history.items():
        result = evaluate_support_zone_ticker(df)
        if result is None or not result.matches:
            continue
        result.ticker = ticker

        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as exc:
            logger.warning("Could not fetch sector/industry for %s: %s", ticker, exc)
            info = {}
        time.sleep(0.3)

        sector = info.get("sector", "")
        industry = info.get("industry", "")
        if is_excluded(sector, industry):
            continue

        matches.append({
            "ticker": ticker,
            "company": ticker_to_company.get(ticker, ticker),
            "sector": sector,
            "industry": industry,
            "close": result.close,
            "rsi14": result.rsi14,
            "bb_lower": result.lower_band,
            "bb_mid": result.mid_band,
            "bb_upper": result.upper_band,
            "avg_daily_value_cr": result.avg_daily_value_20d / 1e7,
        })

    return {
        "matches": matches,
        "universe_size": len(tickers),
        "history_fetched": len(history),
    }
