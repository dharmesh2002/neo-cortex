"""Bollinger Band Breakout Buy Strategy — momentum continuation (buy side only).

Setup: BB Breakout Buy
- Close >= upper Bollinger Band (20-period, 2 std) — price breaks out above the band
- Volume spike: today's volume > prior 20-day average (confirms real participation)
- RSI(14) between 55 and 75 — strong momentum, not extreme overbought (>75 = chasing)
- Close above 200-day SMA (trend alignment)
- Average volume >= 5 lakh shares/day and >= Rs 20cr/day liquidity

Entry  : Next candle open (signal candle close is the trigger)
Target : Upper band + 1× half-width (upper − mid) — riding the band expansion
Stop   : Mid band — if price falls back inside the band, the breakout failed
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from .indicators import bollinger_bands, rsi

logger = logging.getLogger(__name__)

BB_WINDOW = 20
RSI_PERIOD = 14
RSI_MIN = 55.0
RSI_MAX = 75.0
MIN_VOLUME_SHARES = 500_000
LIQUIDITY_THRESHOLD_INR = 20 * 1e7
MIN_HISTORY_ROWS = 60
NEAR_MISS_BAND_PROXIMITY_PCT = 1.0   # close within 1% of upper band → watchlist


@dataclass
class BBBreakoutCandidate:
    ticker: str
    close: float
    upper_band: float
    mid_band: float
    lower_band: float
    rsi14: float
    sma200: float
    volume_today: float
    avg_volume_20d: float
    avg_daily_value_cr: float

    close_above_upper: bool   # close >= upper_band
    rsi_in_range: bool        # RSI_MIN <= rsi14 <= RSI_MAX
    volume_spike: bool        # volume_today > avg_volume_20d
    above_200sma: bool        # close > sma200
    liquidity_ok: bool
    min_volume_ok: bool

    @property
    def matches(self) -> bool:
        return (self.close_above_upper and self.rsi_in_range and
                self.volume_spike and self.above_200sma and
                self.liquidity_ok and self.min_volume_ok)

    @property
    def near_miss(self) -> bool:
        if self.matches:
            return False
        # Close within 1% below upper band, RSI in range, trend OK
        pct_below = (self.upper_band - self.close) / self.upper_band * 100
        return (pct_below <= NEAR_MISS_BAND_PROXIMITY_PCT and
                self.rsi_in_range and self.above_200sma and
                self.liquidity_ok and self.min_volume_ok)

    @property
    def target(self) -> float:
        half_width = self.upper_band - self.mid_band
        return self.upper_band + half_width

    @property
    def stop_loss(self) -> float:
        return self.mid_band

    @property
    def pct_to_target(self) -> float:
        return (self.target - self.close) / self.close * 100

    @property
    def pct_stop_distance(self) -> float:
        return (self.close - self.stop_loss) / self.close * 100

    @property
    def risk_reward(self) -> float:
        if self.pct_stop_distance == 0:
            return 0.0
        return round(self.pct_to_target / self.pct_stop_distance, 2)


def evaluate_bb_breakout_ticker(df: pd.DataFrame) -> Optional[BBBreakoutCandidate]:
    df = df.dropna(subset=["Close", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close = df["Close"]
    volume = df["Volume"]

    mid, upper, lower = bollinger_bands(close, window=BB_WINDOW)
    rsi_series = rsi(close, period=RSI_PERIOD)
    sma200 = close.rolling(window=200).mean()
    avg_volume_20d = volume.shift(1).rolling(window=20).mean()
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()

    if (pd.isna(upper.iloc[-1]) or pd.isna(mid.iloc[-1]) or
            pd.isna(rsi_series.iloc[-1]) or pd.isna(sma200.iloc[-1]) or
            pd.isna(avg_volume_20d.iloc[-1])):
        return None

    close_today = float(close.iloc[-1])
    upper_today = float(upper.iloc[-1])
    mid_today = float(mid.iloc[-1])
    lower_today = float(lower.iloc[-1])
    rsi_today = float(rsi_series.iloc[-1])
    sma200_today = float(sma200.iloc[-1])
    vol_today = float(volume.iloc[-1])
    avg_vol = float(avg_volume_20d.iloc[-1])
    avg_val = float(avg_daily_value_20d.iloc[-1])

    return BBBreakoutCandidate(
        ticker="",
        close=close_today,
        upper_band=upper_today,
        mid_band=mid_today,
        lower_band=lower_today,
        rsi14=rsi_today,
        sma200=sma200_today,
        volume_today=vol_today,
        avg_volume_20d=avg_vol,
        avg_daily_value_cr=avg_val / 1e7,
        close_above_upper=bool(close_today >= upper_today),
        rsi_in_range=bool(RSI_MIN <= rsi_today <= RSI_MAX),
        volume_spike=bool(vol_today > avg_vol),
        above_200sma=bool(close_today > sma200_today),
        liquidity_ok=bool(avg_val >= LIQUIDITY_THRESHOLD_INR),
        min_volume_ok=bool(avg_vol >= MIN_VOLUME_SHARES),
    )


def run_bb_breakout_screen(csv_dir: str = None, info_sleep_seconds: float = 0.3,
                            nifty100_only: bool = False) -> Dict:
    import time

    import yfinance as yf

    from .bb_buy_strategy import NIFTY100_INDICES
    from .screener import fetch_price_history
    from .universe import build_universe, is_excluded

    universe = build_universe(csv_dir=csv_dir)
    if nifty100_only:
        universe = universe[universe["Index"].isin(NIFTY100_INDICES)].reset_index(drop=True)
        logger.info("Nifty 100 filter applied: %d tickers", len(universe))
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    technical_pass: List[tuple] = []
    for ticker, df in history.items():
        result = evaluate_bb_breakout_ticker(df)
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
            "upper_band": result.upper_band,
            "mid_band": result.mid_band,
            "rsi14": result.rsi14,
            "sma200": result.sma200,
            "volume_today_L": round(result.volume_today / 1e5, 2),
            "avg_volume_20d_L": round(result.avg_volume_20d / 1e5, 2),
            "avg_daily_value_cr": result.avg_daily_value_cr,
            "stop_loss": result.stop_loss,
            "target": result.target,
            "pct_to_target": result.pct_to_target,
            "pct_stop_distance": result.pct_stop_distance,
            "risk_reward": result.risk_reward,
            "volume_spike": result.volume_spike,
        }

        if result.matches:
            matches.append(row)
        else:
            near_miss.append(row)

    # Sort by RSI descending — strongest momentum first
    matches.sort(key=lambda r: r["rsi14"], reverse=True)
    near_miss.sort(key=lambda r: r["rsi14"], reverse=True)

    return {
        "matches": matches,
        "near_miss": near_miss,
        "universe_size": len(tickers),
        "history_fetched": len(history),
        "nifty100_only": nifty100_only,
    }
