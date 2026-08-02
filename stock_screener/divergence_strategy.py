"""Detects bullish RSI divergence: price makes a lower swing low while
RSI(14) makes a higher (or equal) low at the same time -- a classic signal
that downward momentum is fading even though price is still falling, often
read as a sign a reversal may be near. Pure price/RSI pattern detection, no
fundamentals.
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from .indicators import rsi

logger = logging.getLogger(__name__)

SWING_WINDOW = 3           # days on each side to qualify as a local swing low
LOOKBACK_DAYS = 90         # how far back to search for swing lows
MAX_RECENT_DAYS = 12       # the more recent swing low must be within this many days of today
MIN_GAP_BETWEEN_LOWS = 5   # minimum trading days between the two compared lows
RSI_CEILING_FOR_LOWS = 50  # both swing lows' RSI must be below this to count as a real dip
LIQUIDITY_THRESHOLD_INR = 20 * 1e7  # 20 crore, same liquidity bar used elsewhere
MIN_HISTORY_ROWS = 100
RSI_PERIOD = 14


def _find_swing_lows(close: pd.Series, window: int = SWING_WINDOW) -> List[int]:
    """Integer positions (via .iloc) where Close is the lowest value within
    +/- window trading days -- a simple local-minimum finder, no external
    peak-detection dependency. Adjacent/tied detections (e.g. a flat
    multi-day consolidation at the same low) are merged into a single
    representative point, otherwise one genuine trough gets counted as many
    separate "swing lows" and pollutes the search for distinct dips."""
    n = len(close)
    raw = []
    for i in range(window, n - window):
        segment = close.iloc[i - window:i + window + 1]
        seg_min, seg_max = segment.min(), segment.max()
        # A perfectly flat segment (no real variation) isn't a genuine dip --
        # without this, a flat plateau trivially satisfies "local minimum"
        # everywhere in it and manufactures a spurious swing low.
        if close.iloc[i] <= seg_min and seg_min < seg_max:
            raw.append(i)
    if not raw:
        return []

    clusters: List[List[int]] = [[raw[0]]]
    for idx in raw[1:]:
        if idx - clusters[-1][-1] <= window * 2:
            clusters[-1].append(idx)
        else:
            clusters.append([idx])

    return [min(cluster, key=lambda i: close.iloc[i]) for cluster in clusters]


@dataclass
class DivergenceCandidate:
    ticker: str
    close: float
    rsi_today: float
    low1_price: float
    low1_rsi: float
    low2_price: float
    low2_rsi: float
    days_since_low2: int
    price_change_pct: float
    rsi_change: float
    avg_daily_value_20d: float


def find_bullish_divergence(df: pd.DataFrame) -> Optional[DivergenceCandidate]:
    df = df.dropna(subset=["Close", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close, volume = df["Close"], df["Volume"]
    rsi_series = rsi(close, period=RSI_PERIOD)
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()

    if pd.isna(avg_daily_value_20d.iloc[-1]) or avg_daily_value_20d.iloc[-1] < LIQUIDITY_THRESHOLD_INR:
        return None

    n = len(close)
    lookback_start = max(0, n - LOOKBACK_DAYS)
    recent_close = close.iloc[lookback_start:]
    recent_rsi = rsi_series.iloc[lookback_start:]

    swing_positions = sorted(_find_swing_lows(recent_close))
    if len(swing_positions) < 2:
        return None

    # Most recent swing low, paired with the most recent *other* swing low
    # that's far enough back to be a genuinely separate dip, not noise.
    idx2 = swing_positions[-1]
    idx1 = None
    for j in range(len(swing_positions) - 2, -1, -1):
        if idx2 - swing_positions[j] >= MIN_GAP_BETWEEN_LOWS:
            idx1 = swing_positions[j]
            break
    if idx1 is None:
        return None

    days_since_low2 = (len(recent_close) - 1) - idx2
    if days_since_low2 > MAX_RECENT_DAYS:
        return None

    low1_rsi = recent_rsi.iloc[idx1]
    low2_rsi = recent_rsi.iloc[idx2]
    if pd.isna(low1_rsi) or pd.isna(low2_rsi):
        return None
    low1_rsi, low2_rsi = float(low1_rsi), float(low2_rsi)
    if low1_rsi > RSI_CEILING_FOR_LOWS or low2_rsi > RSI_CEILING_FOR_LOWS:
        return None

    low1_price = float(recent_close.iloc[idx1])
    low2_price = float(recent_close.iloc[idx2])

    price_lower_low = low2_price < low1_price
    rsi_higher_low = low2_rsi > low1_rsi
    if not (price_lower_low and rsi_higher_low):
        return None

    return DivergenceCandidate(
        ticker="",
        close=float(close.iloc[-1]),
        rsi_today=float(rsi_series.iloc[-1]),
        low1_price=low1_price,
        low1_rsi=low1_rsi,
        low2_price=low2_price,
        low2_rsi=low2_rsi,
        days_since_low2=days_since_low2,
        price_change_pct=(low2_price - low1_price) / low1_price * 100,
        rsi_change=low2_rsi - low1_rsi,
        avg_daily_value_20d=float(avg_daily_value_20d.iloc[-1]),
    )


def run_divergence_screen(csv_dir: str = None, info_sleep_seconds: float = 0.3) -> Dict:
    from .screener import fetch_price_history
    from .universe import build_universe, is_excluded

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    matches: List[dict] = []
    for ticker, df in history.items():
        cand = find_bullish_divergence(df)
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
            "rsi_today": cand.rsi_today,
            "low1_price": cand.low1_price,
            "low1_rsi": cand.low1_rsi,
            "low2_price": cand.low2_price,
            "low2_rsi": cand.low2_rsi,
            "price_change_pct": cand.price_change_pct,
            "rsi_change": cand.rsi_change,
            "days_since_low2": cand.days_since_low2,
            "avg_daily_value_cr": cand.avg_daily_value_20d / 1e7,
        })

    matches.sort(key=lambda r: r["days_since_low2"])

    return {
        "matches": matches,
        "universe_size": len(tickers),
        "history_fetched": len(history),
    }
