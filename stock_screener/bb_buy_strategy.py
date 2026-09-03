"""Bollinger Band Buy-Side Intraday Strategy — mean-reversion bounce (buy side only).

Setup: BB Bounce Buy
- Signal candle low touches or crosses the lower Bollinger Band (20-period, 2 std)
- RSI(14) < 40 (oversold confirmation)
- Volume spike: today's volume > prior 20-day average volume
- Stock above 200-day SMA (uptrend only — buy pullbacks, not breakdowns)
- Average daily volume >= 5 lakh shares and >= Rs 20cr/day liquidity

Entry  : Next candle open (signal candle close is the trigger)
Target : Middle band (20-day SMA) — typically 1–1.5% above entry
Stop   : Low of signal candle — typically 0.4–0.5% below entry
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from .indicators import bollinger_bands, rsi

logger = logging.getLogger(__name__)

BB_WINDOW = 20
RSI_PERIOD = 14
RSI_OVERSOLD = 40.0
MIN_VOLUME_SHARES = 500_000          # 5 lakh shares/day
LIQUIDITY_THRESHOLD_INR = 20 * 1e7  # Rs 20 crore/day
MIN_HISTORY_ROWS = 60                # enough history for 200-day SMA warmup
NEAR_MISS_RSI_MAX = 45.0             # RSI 40–45 → watchlist (close but not quite)
NEAR_MISS_BAND_PROXIMITY_PCT = 1.0   # close within 1% of lower band → watchlist


@dataclass
class BBBuyCandidate:
    ticker: str
    close: float
    low: float
    lower_band: float
    mid_band: float
    upper_band: float
    rsi14: float
    sma200: float
    volume_today: float
    avg_volume_20d: float
    avg_daily_value_cr: float

    low_touched_band: bool   # low <= lower_band
    rsi_oversold: bool       # rsi14 < RSI_OVERSOLD
    volume_spike: bool       # volume_today > avg_volume_20d
    above_200sma: bool       # close > sma200
    liquidity_ok: bool       # avg_daily_value >= LIQUIDITY_THRESHOLD_INR
    min_volume_ok: bool      # avg_volume_20d >= MIN_VOLUME_SHARES

    @property
    def matches(self) -> bool:
        return (self.low_touched_band and self.rsi_oversold and
                self.volume_spike and self.above_200sma and
                self.liquidity_ok and self.min_volume_ok)

    @property
    def near_miss(self) -> bool:
        if self.matches:
            return False
        close_near_band = (
            (self.close - self.lower_band) / self.lower_band * 100
            <= NEAR_MISS_BAND_PROXIMITY_PCT
        )
        return (close_near_band and self.rsi14 <= NEAR_MISS_RSI_MAX and
                self.above_200sma and self.liquidity_ok and self.min_volume_ok)

    @property
    def pct_to_target(self) -> float:
        return (self.mid_band - self.close) / self.close * 100

    @property
    def pct_stop_distance(self) -> float:
        return (self.close - self.low) / self.close * 100

    @property
    def risk_reward(self) -> float:
        if self.pct_stop_distance == 0:
            return 0.0
        return round(self.pct_to_target / self.pct_stop_distance, 2)


def evaluate_bb_buy_ticker(df: pd.DataFrame) -> Optional[BBBuyCandidate]:
    df = df.dropna(subset=["Close", "Low", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close = df["Close"]
    low = df["Low"]
    volume = df["Volume"]

    mid, upper, lower = bollinger_bands(close, window=BB_WINDOW)
    rsi_series = rsi(close, period=RSI_PERIOD)
    sma200 = close.rolling(window=200).mean()
    avg_volume_20d = volume.shift(1).rolling(window=20).mean()
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()

    if (pd.isna(mid.iloc[-1]) or pd.isna(lower.iloc[-1]) or
            pd.isna(rsi_series.iloc[-1]) or pd.isna(sma200.iloc[-1]) or
            pd.isna(avg_volume_20d.iloc[-1])):
        return None

    close_today = float(close.iloc[-1])
    low_today = float(low.iloc[-1])
    lower_today = float(lower.iloc[-1])
    mid_today = float(mid.iloc[-1])
    upper_today = float(upper.iloc[-1])
    rsi_today = float(rsi_series.iloc[-1])
    sma200_today = float(sma200.iloc[-1])
    vol_today = float(volume.iloc[-1])
    avg_vol = float(avg_volume_20d.iloc[-1])
    avg_val = float(avg_daily_value_20d.iloc[-1])

    return BBBuyCandidate(
        ticker="",
        close=close_today,
        low=low_today,
        lower_band=lower_today,
        mid_band=mid_today,
        upper_band=upper_today,
        rsi14=rsi_today,
        sma200=sma200_today,
        volume_today=vol_today,
        avg_volume_20d=avg_vol,
        avg_daily_value_cr=avg_val / 1e7,
        low_touched_band=bool(low_today <= lower_today),
        rsi_oversold=bool(rsi_today < RSI_OVERSOLD),
        volume_spike=bool(vol_today > avg_vol),
        above_200sma=bool(close_today > sma200_today),
        liquidity_ok=bool(avg_val >= LIQUIDITY_THRESHOLD_INR),
        min_volume_ok=bool(avg_vol >= MIN_VOLUME_SHARES),
    )


def run_bb_buy_screen(csv_dir: str = None, info_sleep_seconds: float = 0.3) -> Dict:
    import time

    import yfinance as yf

    from .screener import fetch_price_history
    from .universe import build_universe, is_excluded

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    technical_pass: List[tuple] = []
    for ticker, df in history.items():
        result = evaluate_bb_buy_ticker(df)
        if result is None:
            continue
        result.ticker = ticker
        if result.matches or result.near_miss:
            technical_pass.append((ticker, result))

    matches: List[dict] = []
    near_miss: List[dict] = []

    for ticker, result in technical_pass:
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

        row = {
            "ticker": ticker,
            "company": ticker_to_company.get(ticker, ticker),
            "sector": sector,
            "industry": industry,
            "close": result.close,
            "low": result.low,
            "stop_loss": result.low,
            "target": result.mid_band,
            "lower_band": result.lower_band,
            "mid_band": result.mid_band,
            "rsi14": result.rsi14,
            "sma200": result.sma200,
            "volume_today_L": round(result.volume_today / 1e5, 2),
            "avg_volume_20d_L": round(result.avg_volume_20d / 1e5, 2),
            "avg_daily_value_cr": result.avg_daily_value_cr,
            "pct_to_target": result.pct_to_target,
            "pct_stop_distance": result.pct_stop_distance,
            "risk_reward": result.risk_reward,
            "volume_spike": result.volume_spike,
            "above_200sma": result.above_200sma,
        }

        if result.matches:
            matches.append(row)
        else:
            near_miss.append(row)

    matches.sort(key=lambda r: r["rsi14"])
    near_miss.sort(key=lambda r: r["rsi14"])

    return {
        "matches": matches,
        "near_miss": near_miss,
        "universe_size": len(tickers),
        "history_fetched": len(history),
    }
