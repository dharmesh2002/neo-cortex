"""Capitulation / seller-exhaustion screener.

Looks for the classic "selling climax" sequence: one outsized red candle on
much-heavier-than-usual volume (sellers throwing everything at once) that
price hasn't undercut by much since -- the capitulation candle + a
stabilization check is a hard gate, not a scored signal, since a ticker
either had one recently or it didn't.

On top of that gate, seven independent signals are scored 0-7 to judge how
convincingly selling pressure is fading:

Price action
  - Lower-wick rejections since the capitulation day (price keeps probing
    lower intraday but closes back up -- buyers defending a level).
  - Higher lows forming since the capitulation day (each subsequent dip is
    shallower, even if price is still below its highs).

Volume
  - Selling volume shrinking -- any down day since the capitulation day has
    less volume than the down day before it (sellers running out; a ticker
    with zero down days since then counts as trivially true -- no renewed
    selling at all).
  - Volume absorption -- today's volume is back below its trailing 20-day
    average, i.e. the panic has cooled off from the capitulation spike.

Indicators
  - RSI(14) bullish divergence at the capitulation low itself: price made a
    lower low there than the last confirmed swing low before it, but RSI
    didn't -- momentum of selling was already weaker even at the worst
    print.
  - MACD histogram shrinking in magnitude while still negative -- bearish
    momentum fading, not yet flipped positive.
  - Lower Bollinger Band "walk" stopping: price was closing at/below the
    lower band on multiple days into the capitulation candle, and hasn't
    closed there since.

capitulation_quality tiers the 0-7 confirming score (strong >=6, moderate
>=4, developing >=2, weak <2); MATCH_SCORE_THRESHOLD/NEAR_MISS_SCORE_THRESHOLD
below control what counts as a full match vs. a near-miss watchlist entry.
This is a new, untested pattern -- no backtest exists for it yet. Not
investment advice.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from .indicators import bollinger_bands, macd, rsi

logger = logging.getLogger(__name__)

# ── Anchor: the capitulation candle itself ──
ANCHOR_LOOKBACK_DAYS = 20            # how far back to search for a qualifying capitulation day
ANCHOR_MIN_DECLINE_PCT = 5.0         # candle's own close-vs-prior-close decline, in %
ANCHOR_MIN_VOLUME_MULT = 2.0         # volume vs. the trailing 20-day average volume before that day
MIN_DAYS_SINCE_ANCHOR = 2            # need room afterward to judge "then price stabilizes"
STABILIZATION_TOLERANCE_PCT = 3.0    # allowed undercut of the anchor day's low since then

# ── Confirming signals ──
WICK_REJECTION_RATIO = 0.35          # lower wick as a fraction of the day's high-low range
WICK_REJECTION_MIN_DAYS = 2          # this many qualifying days since the anchor -> signal true
SWING_WINDOW = 3                     # local-minimum window for higher-lows / divergence checks
MIN_GAP_BETWEEN_LOWS = 5             # trading days required between two compared swing lows
BB_WINDOW = 20
RSI_PERIOD = 14

LIQUIDITY_THRESHOLD_INR = 20 * 1e7   # 20 crore, same liquidity bar used elsewhere in this project
MIN_HISTORY_ROWS = 120               # room for the anchor lookback + a prior swing low well before it
MATCH_SCORE_THRESHOLD = 4            # >= this many of 7 confirming signals -> full match
NEAR_MISS_SCORE_THRESHOLD = 2        # >= this many (but below match) -> near-miss watchlist


@dataclass
class CapitulationCandidate:
    ticker: str
    close: float
    pct_change_today: float
    anchor_date: str
    days_since_anchor: int
    anchor_decline_pct: float
    anchor_volume_multiple: float
    post_anchor_undercut_pct: float
    lower_wick_rejection: bool
    wick_rejection_days: int
    higher_lows: bool
    selling_volume_shrinking: bool
    volume_absorption: bool
    rsi_divergence: bool
    macd_histogram_shrinking: bool
    bb_walk_stopped: bool
    price_action_score: int
    volume_score: int
    indicator_score: int
    total_score: int
    capitulation_quality: str
    avg_daily_value_20d: float


def _find_swing_lows(close: pd.Series, window: int = SWING_WINDOW) -> List[int]:
    """Integer positions (via .iloc) where Close is the lowest value within
    +/- window trading days. Flat/tied local minima are merged into a single
    representative point so a multi-day plateau doesn't manufacture many
    spurious swing lows."""
    n = len(close)
    raw = []
    for i in range(window, n - window):
        segment = close.iloc[i - window:i + window + 1]
        seg_min, seg_max = segment.min(), segment.max()
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


def _find_anchor(close: pd.Series, open_: pd.Series, volume: pd.Series) -> Optional[int]:
    """Most recent day within the lookback window that closed down at least
    ANCHOR_MIN_DECLINE_PCT% on at least ANCHOR_MIN_VOLUME_MULT x its trailing
    20-day average volume, with enough days left after it to judge whether
    price actually stabilized."""
    n = len(close)
    avg_volume_prior20 = volume.shift(1).rolling(window=20).mean()
    earliest = max(20, n - ANCHOR_LOOKBACK_DAYS)
    latest = n - MIN_DAYS_SINCE_ANCHOR
    for i in range(latest - 1, earliest - 1, -1):
        prev_close = close.iloc[i - 1]
        if prev_close <= 0 or pd.isna(avg_volume_prior20.iloc[i]) or avg_volume_prior20.iloc[i] <= 0:
            continue
        decline_pct = (close.iloc[i] - prev_close) / prev_close * 100
        volume_mult = volume.iloc[i] / avg_volume_prior20.iloc[i]
        is_red = close.iloc[i] < open_.iloc[i]
        if is_red and decline_pct <= -ANCHOR_MIN_DECLINE_PCT and volume_mult >= ANCHOR_MIN_VOLUME_MULT:
            return i
    return None


def evaluate_ticker(df: pd.DataFrame) -> Optional[CapitulationCandidate]:
    df = df.dropna(subset=["Close", "Open", "High", "Low", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close, open_, high, low, volume = df["Close"], df["Open"], df["High"], df["Low"], df["Volume"]
    n = len(df)

    avg_daily_value_20d = (close * volume).rolling(window=20).mean().iloc[-1]
    if pd.isna(avg_daily_value_20d) or avg_daily_value_20d < LIQUIDITY_THRESHOLD_INR:
        return None

    idx = _find_anchor(close, open_, volume)
    if idx is None:
        return None

    anchor_low = float(low.iloc[idx])
    anchor_close = float(close.iloc[idx])
    prev_close = float(close.iloc[idx - 1])
    anchor_decline_pct = (anchor_close - prev_close) / prev_close * 100
    avg_volume_prior20 = volume.shift(1).rolling(window=20).mean()
    anchor_volume_multiple = float(volume.iloc[idx] / avg_volume_prior20.iloc[idx])

    # "Then price stabilizes" -- reject if the close has since undercut the
    # anchor day's low by more than the allowed tolerance, i.e. sellers
    # weren't actually done.
    post_anchor_min_close = float(close.iloc[idx + 1:].min())
    post_anchor_undercut_pct = (post_anchor_min_close - anchor_low) / anchor_low * 100
    if post_anchor_undercut_pct < -STABILIZATION_TOLERANCE_PCT:
        return None

    days_since_anchor = (n - 1) - idx

    # -- Price action: lower-wick rejections since the anchor --
    wick_days = 0
    for i in range(idx, n):
        rng = float(high.iloc[i] - low.iloc[i])
        if rng <= 0:
            continue
        lower_wick = float(min(open_.iloc[i], close.iloc[i]) - low.iloc[i])
        wick_ratio = lower_wick / rng
        close_position = float(close.iloc[i] - low.iloc[i]) / rng
        if wick_ratio >= WICK_REJECTION_RATIO and close_position >= 0.5:
            wick_days += 1
    lower_wick_rejection = wick_days >= WICK_REJECTION_MIN_DAYS

    # -- Price action: higher lows forming since the anchor (compared on a
    # consistent basis -- the anchor's own close, then each later confirmed
    # swing-low close) --
    later_lows = sorted(i for i in _find_swing_lows(close) if i > idx)
    low_sequence = [anchor_close] + [float(close.iloc[i]) for i in later_lows]
    higher_lows = len(low_sequence) >= 2 and all(
        b > a for a, b in zip(low_sequence, low_sequence[1:])
    )

    # -- Volume: selling volume shrinking on any down day since the anchor.
    # No down days at all since the anchor counts as trivially true -- no
    # renewed selling pressure to shrink from. --
    down_day_volumes = [
        float(volume.iloc[i]) for i in range(idx + 1, n) if close.iloc[i] < close.iloc[i - 1]
    ]
    selling_volume_shrinking = all(
        b <= a for a, b in zip(down_day_volumes, down_day_volumes[1:])
    ) if down_day_volumes else True

    # -- Volume: today's volume back below its recent average (the panic has
    # cooled off from the capitulation spike) --
    avg_volume_today = avg_volume_prior20.iloc[-1]
    volume_absorption = bool(pd.notna(avg_volume_today) and volume.iloc[-1] < avg_volume_today)

    # -- Indicator: RSI higher low vs. the last confirmed swing low before
    # the anchor -- price made a lower low at the capitulation candle than
    # its prior swing low, but RSI didn't. --
    rsi_series = rsi(close, period=RSI_PERIOD)
    prior_lows = [i for i in _find_swing_lows(close) if i <= idx - MIN_GAP_BETWEEN_LOWS]
    rsi_divergence = False
    if prior_lows:
        prior_idx = max(prior_lows)
        prior_rsi, anchor_rsi = rsi_series.iloc[prior_idx], rsi_series.iloc[idx]
        if pd.notna(prior_rsi) and pd.notna(anchor_rsi):
            rsi_divergence = bool(anchor_close < float(close.iloc[prior_idx]) and anchor_rsi > prior_rsi)

    # -- Indicator: MACD histogram shrinking in magnitude while still
    # negative -- bearish momentum fading, comparing the last 3 days'
    # average magnitude to the 3 days before that (smooths single-day noise) --
    _, _, hist = macd(close)
    macd_histogram_shrinking = False
    hist_tail = hist.iloc[-6:]
    if len(hist_tail.dropna()) == 6:
        recent_mag = hist_tail.iloc[-3:].abs().mean()
        older_mag = hist_tail.iloc[:3].abs().mean()
        macd_histogram_shrinking = bool(hist_tail.iloc[-1] < 0 and recent_mag < older_mag)

    # -- Indicator: price was closing at/below the lower Bollinger Band on
    # multiple days into the anchor candle (a "walk" down the band), and
    # hasn't closed there since --
    _, _, bb_lower = bollinger_bands(close, window=BB_WINDOW)
    pre_window = range(max(0, idx - 4), idx + 1)
    walked_before = sum(
        1 for i in pre_window if pd.notna(bb_lower.iloc[i]) and close.iloc[i] <= bb_lower.iloc[i]
    ) >= 2
    post_window = range(idx + 1, n)
    stopped_after = all(
        pd.isna(bb_lower.iloc[i]) or close.iloc[i] > bb_lower.iloc[i] for i in post_window
    )
    bb_walk_stopped = bool(walked_before and stopped_after)

    price_action_score = int(lower_wick_rejection) + int(higher_lows)
    volume_score = int(selling_volume_shrinking) + int(volume_absorption)
    indicator_score = int(rsi_divergence) + int(macd_histogram_shrinking) + int(bb_walk_stopped)
    total_score = price_action_score + volume_score + indicator_score

    if total_score >= 6:
        quality = "strong"
    elif total_score >= 4:
        quality = "moderate"
    elif total_score >= 2:
        quality = "developing"
    else:
        quality = "weak"

    close_today = float(close.iloc[-1])
    pct_change_today = float((close_today / float(close.iloc[-2]) - 1) * 100) if close.iloc[-2] else 0.0

    return CapitulationCandidate(
        ticker="",
        close=close_today,
        pct_change_today=pct_change_today,
        anchor_date=str(df.index[idx].date()) if hasattr(df.index[idx], "date") else str(df.index[idx]),
        days_since_anchor=days_since_anchor,
        anchor_decline_pct=anchor_decline_pct,
        anchor_volume_multiple=anchor_volume_multiple,
        post_anchor_undercut_pct=post_anchor_undercut_pct,
        lower_wick_rejection=lower_wick_rejection,
        wick_rejection_days=wick_days,
        higher_lows=higher_lows,
        selling_volume_shrinking=selling_volume_shrinking,
        volume_absorption=volume_absorption,
        rsi_divergence=rsi_divergence,
        macd_histogram_shrinking=macd_histogram_shrinking,
        bb_walk_stopped=bb_walk_stopped,
        price_action_score=price_action_score,
        volume_score=volume_score,
        indicator_score=indicator_score,
        total_score=total_score,
        capitulation_quality=quality,
        avg_daily_value_20d=float(avg_daily_value_20d),
    )


def run_capitulation_screen(csv_dir: str = None, info_sleep_seconds: float = 0.3) -> Dict:
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
        if cand is None or cand.total_score < NEAR_MISS_SCORE_THRESHOLD:
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
            "pct_change_today": cand.pct_change_today,
            "anchor_date": cand.anchor_date,
            "days_since_anchor": cand.days_since_anchor,
            "anchor_decline_pct": cand.anchor_decline_pct,
            "anchor_volume_multiple": cand.anchor_volume_multiple,
            "post_anchor_undercut_pct": cand.post_anchor_undercut_pct,
            "lower_wick_rejection": cand.lower_wick_rejection,
            "higher_lows": cand.higher_lows,
            "selling_volume_shrinking": cand.selling_volume_shrinking,
            "volume_absorption": cand.volume_absorption,
            "rsi_divergence": cand.rsi_divergence,
            "macd_histogram_shrinking": cand.macd_histogram_shrinking,
            "bb_walk_stopped": cand.bb_walk_stopped,
            "price_action_score": cand.price_action_score,
            "volume_score": cand.volume_score,
            "indicator_score": cand.indicator_score,
            "total_score": cand.total_score,
            "capitulation_quality": cand.capitulation_quality,
            "avg_daily_value_cr": cand.avg_daily_value_20d / 1e7,
        }

        if cand.total_score >= MATCH_SCORE_THRESHOLD:
            matches.append(row)
        else:
            near_miss.append(row)

    matches.sort(key=lambda r: (-r["total_score"], r["days_since_anchor"]))
    near_miss.sort(key=lambda r: (-r["total_score"], r["days_since_anchor"]))

    return {
        "matches": matches,
        "near_miss": near_miss,
        "universe_size": len(tickers),
        "history_fetched": len(history),
    }
