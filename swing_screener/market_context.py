"""Market-context snapshot: Nifty 50 trend/momentum + India VIX + a one-line
regime label, printed at the top of every report."""

from dataclasses import dataclass

import pandas as pd

from .indicators import adx as adx_ind
from .indicators import ema as ema_ind


@dataclass
class MarketContext:
    nifty_close: float
    nifty_ema200: float
    above_ema200: bool
    range_position_pct: float  # 0 = at 60d low, 100 = at 60d high
    nifty_adx: float
    vix: float
    regime: str

    @property
    def in_lower_half_of_range(self) -> bool:
        return self.range_position_pct < 50.0


def compute_market_context(nifty_df: pd.DataFrame, vix_df: pd.DataFrame, config) -> MarketContext:
    close = nifty_df["Close"].dropna()
    high = nifty_df["High"].dropna()
    low = nifty_df["Low"].dropna()

    ema200 = ema_ind(close, config.nifty_ema_period)
    adx_series = adx_ind(nifty_df["High"], nifty_df["Low"], nifty_df["Close"], config.nifty_adx_period)

    window = config.nifty_range_window
    recent_high = high.iloc[-window:].max()
    recent_low = low.iloc[-window:].min()
    nifty_close = float(close.iloc[-1])

    if recent_high > recent_low:
        range_position_pct = float((nifty_close - recent_low) / (recent_high - recent_low) * 100)
    else:
        range_position_pct = 50.0

    nifty_ema200 = float(ema200.iloc[-1])
    above_ema200 = nifty_close > nifty_ema200
    nifty_adx = float(adx_series.iloc[-1]) if not pd.isna(adx_series.iloc[-1]) else float("nan")

    vix = float(vix_df["Close"].dropna().iloc[-1]) if vix_df is not None and not vix_df.empty else float("nan")

    adx_threshold = config.adx_range_bound_threshold
    if pd.isna(nifty_adx) or nifty_adx < adx_threshold:
        regime = "Range-bound"
    elif above_ema200:
        regime = "Trending up"
    else:
        regime = "Trending down"

    return MarketContext(
        nifty_close=nifty_close,
        nifty_ema200=nifty_ema200,
        above_ema200=above_ema200,
        range_position_pct=range_position_pct,
        nifty_adx=nifty_adx,
        vix=vix,
        regime=regime,
    )
