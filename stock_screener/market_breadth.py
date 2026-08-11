"""Market-breadth snapshot: how many stocks are up vs. down today, broken
down by market-cap segment (Nifty 50 / Next 50 / Midcap 50 / Midcap 150 /
Smallcap 100) and by GICS sector -- independent of every other strategy in
this project. Deliberately ignores the standing sector/industry exclusion
list (Technology/Energy/Airlines/Oil/Gas/etc.) that every trading strategy
here applies, since the point of this view is the whole market's actual
shape today, not a pre-filtered trading universe.
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def _pct_change_today(df) -> float:
    close = df["Close"].dropna()
    if len(close) < 2:
        return None
    prev = close.iloc[-2]
    if not prev:
        return None
    return float((close.iloc[-1] / prev - 1) * 100)


def _breadth_stats(rows: List[dict]) -> Dict:
    if not rows:
        return {"count": 0, "advancers": 0, "decliners": 0, "unchanged": 0, "avg_pct_change": 0.0}
    advancers = sum(1 for r in rows if r["pct_change_today"] > 0)
    decliners = sum(1 for r in rows if r["pct_change_today"] < 0)
    unchanged = sum(1 for r in rows if r["pct_change_today"] == 0)
    avg = sum(r["pct_change_today"] for r in rows) / len(rows)
    return {
        "count": len(rows),
        "advancers": advancers,
        "decliners": decliners,
        "unchanged": unchanged,
        "avg_pct_change": avg,
    }


def run_market_breadth(csv_dir: str = None, info_sleep_seconds: float = 0.15) -> Dict:
    from .screener import fetch_price_history, fetch_sector_industry
    from .universe import build_universe

    universe = build_universe(csv_dir=csv_dir)
    tickers = universe["Ticker"].tolist()
    ticker_to_company = dict(zip(universe["Ticker"], universe.get("Company Name", universe["Symbol"])))
    ticker_to_segment = dict(zip(universe["Ticker"], universe["Index"]))

    history = fetch_price_history(tickers)
    logger.info("Fetched history for %d/%d tickers", len(history), len(tickers))

    rows: List[dict] = []
    for ticker, df in history.items():
        pct = _pct_change_today(df)
        if pct is None:
            continue
        rows.append({
            "ticker": ticker,
            "company": ticker_to_company.get(ticker, ticker),
            "segment": ticker_to_segment.get(ticker, ""),
            "pct_change_today": pct,
        })

    overall = _breadth_stats(rows)

    segments = sorted({r["segment"] for r in rows})
    segment_breadth = []
    for seg in segments:
        seg_rows = [r for r in rows if r["segment"] == seg]
        stats = _breadth_stats(seg_rows)
        stats["segment"] = seg
        segment_breadth.append(stats)
    segment_breadth.sort(key=lambda s: s["avg_pct_change"], reverse=True)

    # Sector fetch is the slow part -- one .info call per ticker that had
    # usable price history, deliberately run for every one of them (not just
    # a filtered subset) since the whole point of this view is unfiltered
    # market breadth.
    for row in rows:
        info = fetch_sector_industry(row["ticker"], info_sleep_seconds)
        row["sector"] = info["sector"] or "Unknown"

    sectors = sorted({r["sector"] for r in rows})
    sector_breadth = []
    for sec in sectors:
        sec_rows = [r for r in rows if r["sector"] == sec]
        stats = _breadth_stats(sec_rows)
        stats["sector"] = sec
        sector_breadth.append(stats)
    sector_breadth.sort(key=lambda s: s["avg_pct_change"], reverse=True)

    ranked = sorted(rows, key=lambda r: r["pct_change_today"], reverse=True)
    top_gainers = ranked[:10]
    top_losers = list(reversed(ranked[-10:])) if len(ranked) >= 10 else list(reversed(ranked))

    return {
        "universe_size": len(tickers),
        "history_fetched": len(history),
        "overall": overall,
        "segment_breadth": segment_breadth,
        "sector_breadth": sector_breadth,
        "top_gainers": top_gainers,
        "top_losers": top_losers,
    }
