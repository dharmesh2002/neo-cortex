"""Pure price-structure screener: peaks (swing highs) and valleys (swing
lows), nothing else -- no RSI, no MACD, no Bollinger Bands, no volume. Reads
a stock's recent chart exactly the way the "rising stairs / falling stairs"
framework does:

- Uptrend: each peak higher than the last (HH) AND each valley higher than
  the last (HL). Buyers in control.
- Downtrend: each peak lower than the last (LH) AND each valley lower than
  the last (LL). Sellers in control.
- Reversal developing (the "first hint"): peaks are still making a lower
  high (LH), but the most recent valley just broke the streak of lower
  lows and came in higher than the one before it (HL). This is literally
  "the moment a stock stops making a lower low."
- Reversal confirmed: the leg right before this one was still LH (i.e. a
  genuine downtrend was in place), the valley in between turned into a HL,
  and now the newest peak has pushed above the previous peak too (HH) --
  both conditions of an uptrend are met for the first time.
- Dead-cat bounce (warning): a valley had turned into a HL (a bounce
  attempt) but the very next valley broke back down into a LL while peaks
  are still LH -- the bounce failed and the downtrend resumed.

Swing points are found with a simple fractal/zigzag method on the actual
High (for peaks) and Low (for valleys) series -- a bar is a peak if it's
the highest High within a window of trading days on each side, a valley if
it's the lowest Low, with same-type runs merged down to their single most
extreme point so peaks and valleys strictly alternate in time.

This is a new, untested pattern -- no backtest exists for it yet. Not
investment advice.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

SWING_WINDOW = 3              # trading days on each side required to confirm a peak/valley
MIN_HISTORY_ROWS = 90         # enough room to find several alternating swings
RECENCY_MAX_DAYS = 15         # the latest confirmed swing must be within this many days of today
LIQUIDITY_THRESHOLD_INR = 20 * 1e7  # 20 crore, same liquidity bar used elsewhere in this project

REVERSAL_STAGES = ("reversal_developing", "reversal_confirmed")


@dataclass
class StructureCandidate:
    ticker: str
    close: float
    stage: str
    peak_trend: str
    valley_trend: str
    peak_prev: float
    peak_prev_date: str
    peak_recent: float
    peak_recent_date: str
    valley_prev: float
    valley_prev_date: str
    valley_recent: float
    valley_recent_date: str
    days_since_last_swing: int
    pct_from_recent_valley: float
    avg_daily_value_20d: float


def _find_extrema(series: pd.Series, window: int, mode: str) -> List[int]:
    """Integer positions (via .iloc) that are a local max ('max', for peaks
    on High) or local min ('min', for valleys on Low) within +/- window
    trading days. Flat/tied runs are merged into their single most extreme
    representative point."""
    n = len(series)
    raw = []
    for i in range(window, n - window):
        segment = series.iloc[i - window:i + window + 1]
        seg_min, seg_max = segment.min(), segment.max()
        if seg_min == seg_max:
            continue
        if mode == "max" and series.iloc[i] >= seg_max:
            raw.append(i)
        elif mode == "min" and series.iloc[i] <= seg_min:
            raw.append(i)
    if not raw:
        return []

    clusters: List[List[int]] = [[raw[0]]]
    for idx in raw[1:]:
        if idx - clusters[-1][-1] <= window * 2:
            clusters[-1].append(idx)
        else:
            clusters.append([idx])
    if mode == "max":
        return [max(cluster, key=lambda i: series.iloc[i]) for cluster in clusters]
    return [min(cluster, key=lambda i: series.iloc[i]) for cluster in clusters]


def _build_zigzag(high: pd.Series, low: pd.Series, window: int = SWING_WINDOW) -> List[Tuple[int, str, float]]:
    """Merge independently-detected peaks (on High) and valleys (on Low)
    into a single time-ordered, strictly alternating sequence -- when two
    same-type candidates appear back to back with no opposite-type point
    between them, only the more extreme one survives."""
    peak_positions = set(_find_extrema(high, window, "max"))
    valley_positions = set(_find_extrema(low, window, "min"))
    events = sorted(
        [(i, "peak", float(high.iloc[i])) for i in peak_positions]
        + [(i, "valley", float(low.iloc[i])) for i in valley_positions]
    )

    zigzag: List[Tuple[int, str, float]] = []
    for idx, kind, price in events:
        if zigzag and zigzag[-1][1] == kind:
            if kind == "peak" and price > zigzag[-1][2]:
                zigzag[-1] = (idx, kind, price)
            elif kind == "valley" and price < zigzag[-1][2]:
                zigzag[-1] = (idx, kind, price)
            # else: less extreme than the point already held -- discard
        else:
            zigzag.append((idx, kind, price))
    return zigzag


def _classify(zigzag: List[Tuple[int, str, float]]) -> Optional[dict]:
    peaks = [(i, p) for i, k, p in zigzag if k == "peak"]
    valleys = [(i, p) for i, k, p in zigzag if k == "valley"]
    if len(peaks) < 2 or len(valleys) < 2:
        return None

    p_prev, p_recent = peaks[-2], peaks[-1]
    v_prev, v_recent = valleys[-2], valleys[-1]

    peak_trend = "HH" if p_recent[1] > p_prev[1] else "LH"
    valley_trend = "HL" if v_recent[1] > v_prev[1] else "LL"

    peak_trend_prior = None
    if len(peaks) >= 3:
        peak_trend_prior = "HH" if peaks[-2][1] > peaks[-3][1] else "LH"
    valley_trend_prior = None
    if len(valleys) >= 3:
        valley_trend_prior = "HL" if valleys[-2][1] > valleys[-3][1] else "LL"

    if peak_trend == "HH" and valley_trend == "HL":
        stage = "reversal_confirmed" if peak_trend_prior == "LH" else "uptrend"
    elif peak_trend == "LH" and valley_trend == "LL":
        stage = "dead_cat_bounce" if valley_trend_prior == "HL" else "downtrend"
    elif peak_trend == "LH" and valley_trend == "HL":
        stage = "reversal_developing"
    else:  # HH + LL
        stage = "topping_developing"

    return {
        "stage": stage,
        "peak_trend": peak_trend,
        "valley_trend": valley_trend,
        "peak_prev": p_prev, "peak_recent": p_recent,
        "valley_prev": v_prev, "valley_recent": v_recent,
    }


def evaluate_ticker(df: pd.DataFrame) -> Optional[StructureCandidate]:
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]
    n = len(df)

    avg_daily_value_20d = (close * volume).rolling(window=20).mean().iloc[-1]
    if pd.isna(avg_daily_value_20d) or avg_daily_value_20d < LIQUIDITY_THRESHOLD_INR:
        return None

    zigzag = _build_zigzag(high, low)
    result = _classify(zigzag)
    if result is None:
        return None

    p_prev_idx, p_prev_price = result["peak_prev"]
    p_recent_idx, p_recent_price = result["peak_recent"]
    v_prev_idx, v_prev_price = result["valley_prev"]
    v_recent_idx, v_recent_price = result["valley_recent"]

    last_swing_idx = max(p_recent_idx, v_recent_idx)
    days_since_last_swing = (n - 1) - last_swing_idx
    if days_since_last_swing > RECENCY_MAX_DAYS:
        return None

    close_today = float(close.iloc[-1])
    pct_from_recent_valley = (
        (close_today - v_recent_price) / v_recent_price * 100 if v_recent_price else 0.0
    )

    return StructureCandidate(
        ticker="",
        close=close_today,
        stage=result["stage"],
        peak_trend=result["peak_trend"],
        valley_trend=result["valley_trend"],
        peak_prev=p_prev_price, peak_prev_date=str(df.index[p_prev_idx].date()),
        peak_recent=p_recent_price, peak_recent_date=str(df.index[p_recent_idx].date()),
        valley_prev=v_prev_price, valley_prev_date=str(df.index[v_prev_idx].date()),
        valley_recent=v_recent_price, valley_recent_date=str(df.index[v_recent_idx].date()),
        days_since_last_swing=days_since_last_swing,
        pct_from_recent_valley=pct_from_recent_valley,
        avg_daily_value_20d=float(avg_daily_value_20d),
    )


def run_trend_structure_screen(csv_dir: str = None, info_sleep_seconds: float = 0.3) -> Dict:
    from .screener import fetch_price_history, fetch_sector_industry
    from .universe import build_universe, is_excluded

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    matches: List[dict] = []
    near_miss: List[dict] = []
    for ticker, df in history.items():
        cand = evaluate_ticker(df)
        if cand is None or cand.stage not in (*REVERSAL_STAGES, "dead_cat_bounce"):
            continue
        cand.ticker = ticker

        sector_info = fetch_sector_industry(ticker, info_sleep_seconds)
        if is_excluded(sector_info["sector"], sector_info["industry"]):
            continue

        row = {
            "ticker": ticker,
            "company": ticker_to_company.get(ticker, ticker),
            "sector": sector_info["sector"],
            "industry": sector_info["industry"],
            "close": cand.close,
            "stage": cand.stage,
            "peak_trend": cand.peak_trend,
            "valley_trend": cand.valley_trend,
            "peak_prev": cand.peak_prev,
            "peak_prev_date": cand.peak_prev_date,
            "peak_recent": cand.peak_recent,
            "peak_recent_date": cand.peak_recent_date,
            "valley_prev": cand.valley_prev,
            "valley_prev_date": cand.valley_prev_date,
            "valley_recent": cand.valley_recent,
            "valley_recent_date": cand.valley_recent_date,
            "days_since_last_swing": cand.days_since_last_swing,
            "pct_from_recent_valley": cand.pct_from_recent_valley,
            "avg_daily_value_cr": cand.avg_daily_value_20d / 1e7,
        }

        if cand.stage in REVERSAL_STAGES:
            matches.append(row)
        else:
            near_miss.append(row)

    stage_rank = {"reversal_confirmed": 0, "reversal_developing": 1}
    matches.sort(key=lambda r: (stage_rank.get(r["stage"], 9), r["days_since_last_swing"]))
    near_miss.sort(key=lambda r: r["days_since_last_swing"])

    return {
        "matches": matches,
        "near_miss": near_miss,
        "universe_size": len(tickers),
        "history_fetched": len(history),
    }
