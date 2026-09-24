"""Core 3-condition swing signal (fixed rules -- do not change), the 5
non-filtering extra checks used only for scoring/sorting, and the near-miss
watchlist (stocks meeting exactly 2 of the 3 core conditions).
"""

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from .indicators import adx as adx_ind
from .indicators import atr as atr_ind
from .indicators import bollinger_bands, rsi as rsi_ind, sma as sma_ind

MIN_HISTORY_ROWS_BUFFER = 10


@dataclass
class CoreEval:
    ticker: str
    symbol: str
    industry: str
    close: float
    prev_close: float
    low: float
    lower_band: float
    upper_band: float
    mid_band: float
    rsi_today: float
    rsi_prev: float
    rsi_min_5d: float
    atr14: float
    volume_today: float
    avg_volume_prior20: float
    avg_value_20d_cr: float
    stock_return_63d: Optional[float]
    stock_adx14: Optional[float]
    bb_condition: bool
    rsi_condition: bool
    volume_condition: bool
    liquidity_ok: bool

    @property
    def core_count(self) -> int:
        return sum([self.bb_condition, self.rsi_condition, self.volume_condition])

    @property
    def missing_core(self) -> List[str]:
        missing = []
        if not self.bb_condition:
            missing.append("Bollinger bounce")
        if not self.rsi_condition:
            missing.append("RSI bounce")
        if not self.volume_condition:
            missing.append("Volume")
        return missing


@dataclass
class ExtraChecks:
    rs: Optional[bool] = None
    sector: Optional[bool] = None
    nifty_range: Optional[bool] = None
    adx: Optional[bool] = None
    delivery: Optional[bool] = None

    @property
    def score(self) -> int:
        return sum(1 for v in (self.rs, self.sector, self.nifty_range, self.adx, self.delivery) if v is True)

    def as_marks(self) -> dict:
        def mark(v):
            if v is True:
                return "✓"  # check
            if v is False:
                return "✗"  # cross
            return "n/a"

        return {
            "RS": mark(self.rs),
            "Sector": mark(self.sector),
            "NiftyRange": mark(self.nifty_range),
            "ADX": mark(self.adx),
            "Delivery": mark(self.delivery),
        }


def evaluate_core(df: pd.DataFrame, symbol: str, industry: str, config) -> Optional[CoreEval]:
    """Evaluate the 3 fixed core conditions + liquidity for one ticker's
    OHLCV history. Returns None if there isn't enough clean history."""
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])

    bb_window = config.bb_window
    rsi_period = config.rsi_period
    rsi_lookback = config.rsi_lookback_days
    volume_window = config.volume_avg_window
    rs_lookback = config.rs_lookback_days
    atr_period = config.atr_period

    min_rows = max(bb_window, rsi_period + rsi_lookback, volume_window, rs_lookback, atr_period) + MIN_HISTORY_ROWS_BUFFER
    if len(df) < min_rows:
        return None

    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]

    mid, upper, lower = bollinger_bands(close, window=bb_window, num_std=config.bb_std)
    rsi_series = rsi_ind(close, period=rsi_period)
    atr_series = atr_ind(high, low, close, period=atr_period)
    adx_series = adx_ind(high, low, close, period=14)

    avg_volume_prior20 = volume.shift(1).rolling(window=volume_window).mean()
    avg_value_20d = (close * volume).rolling(window=20).mean()

    if pd.isna(lower.iloc[-1]) or pd.isna(rsi_series.iloc[-1]) or pd.isna(atr_series.iloc[-1]):
        return None
    if pd.isna(avg_volume_prior20.iloc[-1]) or len(rsi_series) < rsi_lookback + 1:
        return None

    close_today, close_prev = float(close.iloc[-1]), float(close.iloc[-2])
    low_today = float(low.iloc[-1])
    lower_today = float(lower.iloc[-1])
    rsi_today, rsi_prev = float(rsi_series.iloc[-1]), float(rsi_series.iloc[-2])
    rsi_min_5d = float(rsi_series.iloc[-rsi_lookback:].min())

    bb_condition = bool(low_today <= lower_today and close_today > lower_today and close_today > close_prev)
    rsi_condition = bool(rsi_min_5d <= config.rsi_oversold and rsi_today > rsi_prev)
    volume_condition = bool(volume.iloc[-1] > avg_volume_prior20.iloc[-1])
    liquidity_ok = bool(avg_value_20d.iloc[-1] >= config.liquidity_min_value_cr * 1e7)

    stock_return_63d = None
    if len(close) > rs_lookback:
        base = float(close.iloc[-(rs_lookback + 1)])
        if base:
            stock_return_63d = (close_today / base - 1) * 100

    stock_adx14 = float(adx_series.iloc[-1]) if not pd.isna(adx_series.iloc[-1]) else None

    return CoreEval(
        ticker=symbol + ".NS",
        symbol=symbol,
        industry=industry,
        close=close_today,
        prev_close=close_prev,
        low=low_today,
        lower_band=lower_today,
        upper_band=float(upper.iloc[-1]),
        mid_band=float(mid.iloc[-1]),
        rsi_today=rsi_today,
        rsi_prev=rsi_prev,
        rsi_min_5d=rsi_min_5d,
        atr14=float(atr_series.iloc[-1]),
        volume_today=float(volume.iloc[-1]),
        avg_volume_prior20=float(avg_volume_prior20.iloc[-1]),
        avg_value_20d_cr=float(avg_value_20d.iloc[-1]) / 1e7,
        stock_return_63d=stock_return_63d,
        stock_adx14=stock_adx14,
        bb_condition=bb_condition,
        rsi_condition=rsi_condition,
        volume_condition=volume_condition,
        liquidity_ok=liquidity_ok,
    )


def sector_index_above_sma(sector_df: Optional[pd.DataFrame], window: int) -> Optional[bool]:
    """True/False if the sector index closed above its N-day SMA, None
    ('n/a') if the index couldn't be mapped or has insufficient history."""
    if sector_df is None or sector_df.empty:
        return None
    close = sector_df["Close"].dropna()
    if len(close) < window:
        return None
    sma = sma_ind(close, window)
    if pd.isna(sma.iloc[-1]):
        return None
    return bool(close.iloc[-1] > sma.iloc[-1])


def compute_extra_checks(
    core: CoreEval,
    nifty_return_63d: Optional[float],
    sector_above_sma: Optional[bool],
    nifty_lower_half: bool,
    adx_threshold: float,
    delivery_today_pct: Optional[float],
    delivery_avg20_pct: Optional[float],
) -> ExtraChecks:
    rs = None
    if core.stock_return_63d is not None and nifty_return_63d is not None:
        rs = core.stock_return_63d > nifty_return_63d

    adx_check = None if core.stock_adx14 is None else bool(core.stock_adx14 < adx_threshold)

    delivery = None
    if delivery_today_pct is not None and delivery_avg20_pct is not None:
        delivery = bool(delivery_today_pct > delivery_avg20_pct)

    return ExtraChecks(
        rs=rs,
        sector=sector_above_sma,
        nifty_range=bool(nifty_lower_half),
        adx=adx_check,
        delivery=delivery,
    )


def near_miss_detail(core: CoreEval, config) -> str:
    """One-line description of the single missing condition and how close
    it is to triggering, for a stock meeting exactly 2 of the 3 core
    conditions."""
    parts = []
    if not core.bb_condition:
        if core.low > core.lower_band:
            pct_above = (core.low - core.lower_band) / core.lower_band * 100
            parts.append(f"Bollinger: low is {pct_above:.1f}% above the lower band (needs a touch)")
        elif core.close <= core.lower_band:
            parts.append(f"Bollinger: close {core.close:.2f} hasn't recovered above lower band {core.lower_band:.2f}")
        else:
            parts.append(f"Bollinger: close {core.close:.2f} <= prev close {core.prev_close:.2f}")
    if not core.rsi_condition:
        if core.rsi_min_5d > config.rsi_oversold:
            parts.append(f"RSI: min(5d)={core.rsi_min_5d:.1f}, hasn't dipped to <= {config.rsi_oversold}")
        else:
            parts.append(f"RSI: today {core.rsi_today:.1f} not yet above yesterday {core.rsi_prev:.1f}")
    if not core.volume_condition:
        ratio = core.volume_today / core.avg_volume_prior20 * 100 if core.avg_volume_prior20 else 0.0
        parts.append(f"Volume: {ratio:.0f}% of 20d avg (needs > 100%)")
    return "; ".join(parts)
