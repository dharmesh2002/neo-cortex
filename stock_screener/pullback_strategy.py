"""Alternative strategy: quality stocks resting quietly near support, not
chasing an oversold bounce. Looks for stocks sitting between the Bollinger
lower and middle band, within 2% of their 50-day SMA, with strong
fundamentals, and no recent outsized single-day move.

There's no data feed for "affected by the US-Iran war" specifically -- an
unusually large recent single-day move (either direction) is used as the
practical stand-in, since that's how a macro/geopolitical shock typically
shows up in a stock's price. Combined with the existing Energy/Oil/Gas
exclusion list (which already screens out the names most directly exposed
to an oil-price shock), this is the closest computable proxy for "no
external impact."
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from .indicators import bollinger_bands
from .universe import is_excluded

logger = logging.getLogger(__name__)

SMA_SUPPORT_WINDOW = 50
SUPPORT_TOLERANCE_PCT = 0.02  # within 2% of the 50-day SMA
MAX_RECENT_MOVE_PCT = 3.0  # exclude if yesterday's or today's move exceeds this, either direction

# Bounce-quality scoring: none of these change which stocks pass the
# technical/fundamentals gates above -- they're read-only diagnostics that
# answer "if this does turn into a bounce, is it a strong one?" Same three
# signals used to read a bounce candle elsewhere in this project: how close
# the candle closed to its high (close-position-in-range), whether volume
# actually confirmed the move (vs. the trailing 20-day average), and whether
# the stock is outperforming the rest of the screened universe today rather
# than just riding a broad market/sector tailwind.
CLOSE_POSITION_STRONG = 0.65  # (close - low) / (high - low) -- closer to 1.0 = buyers in control
MIN_ROE = 0.15
MAX_DEBT_TO_EQUITY = 100.0
BAD_RECOMMENDATIONS = {"sell", "underperform"}

# Banks/NBFCs run high leverage as their normal business model (deposits and
# borrowings ARE the business, not distress) -- a Debt/Equity ratio that would
# flag a manufacturer as overleveraged is routine for this sector. Applying
# the same MAX_DEBT_TO_EQUITY threshold there would reject nearly the entire
# sector regardless of actual financial health, so the low-debt check is
# skipped (treated as automatically satisfied) for these sectors.
DEBT_CHECK_EXEMPT_SECTORS = {"financial services", "financials"}
LIQUIDITY_THRESHOLD_INR = 20 * 1e7  # 20 crore, same liquidity bar as the bounce strategy
BB_WINDOW = 20
MIN_HISTORY_ROWS = 60


@dataclass
class PullbackCandidate:
    ticker: str
    close: float
    sma50: float
    sma20: float
    lower_band: float
    pct_change_today: float
    pct_change_yesterday: float
    avg_daily_value_20d: float
    near_support: bool
    in_bb_zone: bool
    quiet: bool
    liquidity_ok: bool
    close_position_pct: float = 0.5
    volume_today: float = 0.0
    avg_volume_prior20: float = 0.0
    volume_confirmed: bool = False
    excess_return_pct: float = 0.0
    rs_condition: bool = False
    bounce_quality: str = ""
    tailwind_risk: bool = False

    @property
    def technical_ok(self) -> bool:
        return self.near_support and self.in_bb_zone and self.quiet and self.liquidity_ok


def evaluate_pullback_ticker(df: pd.DataFrame) -> Optional[PullbackCandidate]:
    """Cheap, price-only pre-filter -- no network calls. Fundamentals are only
    fetched for tickers that pass this technical gate."""
    df = df.dropna(subset=["Close", "High", "Low", "Volume"])
    if len(df) < MIN_HISTORY_ROWS:
        return None

    close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]
    sma20, _, lower = bollinger_bands(close, window=BB_WINDOW)
    sma50 = close.rolling(window=SMA_SUPPORT_WINDOW).mean()
    avg_daily_value_20d = (close * volume).rolling(window=20).mean()
    avg_volume_prior20 = volume.shift(1).rolling(window=20).mean()

    if pd.isna(sma50.iloc[-1]) or pd.isna(sma20.iloc[-1]) or pd.isna(lower.iloc[-1]):
        return None
    if len(close) < 3:
        return None

    close_today = close.iloc[-1]
    close_yday = close.iloc[-2]
    close_2d_ago = close.iloc[-3]
    high_today = high.iloc[-1]
    low_today = low.iloc[-1]

    pct_change_today = float((close_today / close_yday - 1) * 100) if close_yday else 0.0
    pct_change_yesterday = float((close_yday / close_2d_ago - 1) * 100) if close_2d_ago else 0.0

    near_support = bool(abs(close_today - sma50.iloc[-1]) / sma50.iloc[-1] <= SUPPORT_TOLERANCE_PCT)
    in_bb_zone = bool(lower.iloc[-1] < close_today < sma20.iloc[-1])
    quiet = bool(
        abs(pct_change_today) <= MAX_RECENT_MOVE_PCT
        and abs(pct_change_yesterday) <= MAX_RECENT_MOVE_PCT
    )
    liquidity_ok = bool(avg_daily_value_20d.iloc[-1] >= LIQUIDITY_THRESHOLD_INR)

    today_range = high_today - low_today
    close_position_pct = float((close_today - low_today) / today_range) if today_range > 0 else 0.5

    avg_vol_prior20_today = avg_volume_prior20.iloc[-1]
    volume_confirmed = bool(not pd.isna(avg_vol_prior20_today) and volume.iloc[-1] > avg_vol_prior20_today)

    return PullbackCandidate(
        ticker="",
        close=float(close_today),
        sma50=float(sma50.iloc[-1]),
        sma20=float(sma20.iloc[-1]),
        lower_band=float(lower.iloc[-1]),
        pct_change_today=pct_change_today,
        pct_change_yesterday=pct_change_yesterday,
        avg_daily_value_20d=float(avg_daily_value_20d.iloc[-1]),
        near_support=near_support,
        in_bb_zone=in_bb_zone,
        quiet=quiet,
        liquidity_ok=liquidity_ok,
        close_position_pct=close_position_pct,
        volume_today=float(volume.iloc[-1]),
        avg_volume_prior20=float(avg_vol_prior20_today) if not pd.isna(avg_vol_prior20_today) else 0.0,
        volume_confirmed=volume_confirmed,
    )


def score_bounce_quality(close_position_pct: float, volume_confirmed: bool, rs_condition: bool) -> str:
    """Tier a candidate by how many of the 3 real bounce-quality signals
    agree: a strong candle close (in the top part of today's range), volume
    above its trailing 20-day average, and outperformance vs. the rest of
    the screened universe today (vs. merely riding a market/sector
    tailwind). Purely informational -- doesn't gate any candidate."""
    strong_signals = sum([
        close_position_pct >= CLOSE_POSITION_STRONG,
        volume_confirmed,
        rs_condition,
    ])
    return {3: "strong", 2: "moderate", 1: "developing", 0: "weak"}[strong_signals]


def fetch_fundamentals(ticker: str, sleep_seconds: float = 0.0) -> Dict:
    """Only called for tickers that already passed the technical gate, since
    .info is a slow, individually-rate-limited call."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        logger.warning("Could not fetch fundamentals for %s: %s", ticker, exc)
        info = {}
    finally:
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return info


def fundamentals_ok(info: Dict, sector: str = "") -> Dict:
    earnings_growth = info.get("earningsGrowth")
    revenue_growth = info.get("revenueGrowth")
    roe = info.get("returnOnEquity")
    debt_to_equity = info.get("debtToEquity")
    recommendation = (info.get("recommendationKey") or "").lower()

    debt_check_exempt = (sector or "").strip().lower() in DEBT_CHECK_EXEMPT_SECTORS

    profitable_and_growing = bool(
        (earnings_growth is not None and earnings_growth > 0)
        or (revenue_growth is not None and revenue_growth > 0)
    )
    efficient = bool(roe is not None and roe > MIN_ROE)
    low_debt = debt_check_exempt or bool(debt_to_equity is not None and debt_to_equity < MAX_DEBT_TO_EQUITY)
    analyst_backed = bool(recommendation and recommendation not in BAD_RECOMMENDATIONS)

    return {
        "profitable_and_growing": profitable_and_growing,
        "efficient_roe": efficient,
        "low_debt": low_debt,
        "analyst_backed": analyst_backed,
        "debt_check_exempt": debt_check_exempt,
        "earnings_growth": earnings_growth,
        "revenue_growth": revenue_growth,
        "roe": roe,
        "debt_to_equity": debt_to_equity,
        "recommendation": recommendation,
    }


def check_fundamentals_for_tickers(tickers: List[str], sleep_seconds: float = 0.3) -> List[dict]:
    """Ad-hoc fundamentals check for an explicit ticker list, independent of
    any technical scan -- e.g. to annotate a shortlist that came from a pure
    price/RSI screen with real fundamentals data. Every ticker is reported,
    passing or not, so nothing is silently dropped."""
    rows: List[dict] = []
    for ticker in tickers:
        info = fetch_fundamentals(ticker, sleep_seconds)
        sector = info.get("sector", "")
        industry = info.get("industry", "")
        f = fundamentals_ok(info, sector=sector)
        overall_ok = bool(
            f["profitable_and_growing"] and f["efficient_roe"]
            and f["low_debt"] and f["analyst_backed"]
        )
        rows.append({
            "ticker": ticker,
            "sector": sector,
            "industry": industry,
            "roe_pct": (f["roe"] * 100) if f["roe"] is not None else None,
            "debt_to_equity": f["debt_to_equity"],
            "debt_check_exempt": f["debt_check_exempt"],
            "earnings_growth_pct": (f["earnings_growth"] * 100) if f["earnings_growth"] is not None else None,
            "revenue_growth_pct": (f["revenue_growth"] * 100) if f["revenue_growth"] is not None else None,
            "recommendation": f["recommendation"],
            "profitable_and_growing": f["profitable_and_growing"],
            "efficient_roe": f["efficient_roe"],
            "low_debt": f["low_debt"],
            "analyst_backed": f["analyst_backed"],
            "overall_ok": overall_ok,
        })
    return rows


def run_pullback_screen(csv_dir: str = None, info_sleep_seconds: float = 0.3) -> Dict:
    """Universe/price-history fetching is shared with the bounce strategy to
    avoid duplicating the niftyindices.com + yfinance plumbing."""
    from .screener import fetch_price_history
    from .universe import build_universe

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    # Pass 1: evaluate every ticker once, and use the whole universe's
    # today's % change as the relative-strength benchmark (same two-pass
    # pattern as the bounce strategy's run_screen).
    evaluated: Dict[str, PullbackCandidate] = {}
    for ticker, df in history.items():
        result = evaluate_pullback_ticker(df)
        if result is None:
            continue
        result.ticker = ticker
        evaluated[ticker] = result

    if evaluated:
        universe_avg_pct_change = sum(r.pct_change_today for r in evaluated.values()) / len(evaluated)
    else:
        universe_avg_pct_change = 0.0

    # Pass 2: score bounce quality now that the RS benchmark is known, then
    # gate on the (unchanged) technical criteria.
    technical_candidates: List[PullbackCandidate] = []
    for result in evaluated.values():
        result.excess_return_pct = result.pct_change_today - universe_avg_pct_change
        result.rs_condition = result.excess_return_pct > 0
        result.tailwind_risk = not result.rs_condition
        result.bounce_quality = score_bounce_quality(
            result.close_position_pct, result.volume_confirmed, result.rs_condition
        )
        if result.technical_ok:
            technical_candidates.append(result)

    matches: List[dict] = []
    rejected: List[dict] = []
    for cand in technical_candidates:
        info = fetch_fundamentals(cand.ticker, info_sleep_seconds)
        sector = info.get("sector", "")
        industry = info.get("industry", "")
        if is_excluded(sector, industry):
            rejected.append({
                "ticker": cand.ticker,
                "company": ticker_to_company.get(cand.ticker, cand.ticker),
                "sector": sector,
                "industry": industry,
                "reason": "excluded sector/industry",
            })
            continue

        f = fundamentals_ok(info, sector=sector)
        failed_checks = [
            name for name, ok in [
                ("profitable_and_growing", f["profitable_and_growing"]),
                ("efficient_roe", f["efficient_roe"]),
                ("low_debt", f["low_debt"]),
                ("analyst_backed", f["analyst_backed"]),
            ] if not ok
        ]

        if failed_checks:
            rejected.append({
                "ticker": cand.ticker,
                "company": ticker_to_company.get(cand.ticker, cand.ticker),
                "sector": sector,
                "industry": industry,
                "reason": ", ".join(failed_checks),
                "roe_pct": (f["roe"] * 100) if f["roe"] is not None else None,
                "debt_to_equity": f["debt_to_equity"],
                "debt_check_exempt": f["debt_check_exempt"],
                "earnings_growth_pct": (f["earnings_growth"] * 100) if f["earnings_growth"] is not None else None,
                "revenue_growth_pct": (f["revenue_growth"] * 100) if f["revenue_growth"] is not None else None,
                "recommendation": f["recommendation"],
            })
            continue

        matches.append({
            "ticker": cand.ticker,
            "company": ticker_to_company.get(cand.ticker, cand.ticker),
            "sector": sector,
            "industry": industry,
            "close": cand.close,
            "sma50_support": cand.sma50,
            "bb_lower": cand.lower_band,
            "bb_mid": cand.sma20,
            "pct_change_today": cand.pct_change_today,
            "roe_pct": (f["roe"] or 0) * 100,
            "debt_to_equity": f["debt_to_equity"],
            "earnings_growth_pct": (f["earnings_growth"] * 100) if f["earnings_growth"] is not None else None,
            "recommendation": f["recommendation"],
            "avg_daily_value_cr": cand.avg_daily_value_20d / 1e7,
            "close_position_pct": cand.close_position_pct * 100,
            "volume_confirmed": cand.volume_confirmed,
            "excess_return_pct": cand.excess_return_pct,
            "bounce_quality": cand.bounce_quality,
            "tailwind_risk": cand.tailwind_risk,
        })

    return {
        "matches": matches,
        "rejected": rejected,
        "universe_size": len(tickers),
        "history_fetched": len(history),
        "technical_candidates": len(technical_candidates),
        "universe_avg_pct_change": universe_avg_pct_change,
    }
