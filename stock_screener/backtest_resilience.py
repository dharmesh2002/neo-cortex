"""Backtest of the Resilience screener's price-signal rules.

What is tested: the 7 price signals (>= MIN_SIGNALS of them, liquidity floor)
and the Top-20 selection (<= 3 per sector, large caps before mid caps),
recomputed every REBALANCE_EVERY sessions using only data up to that day.

What cannot be tested point-in-time, and is therefore left out:
  * Delivery data (info-only in the live strategy anyway; NSE bhavcopy history
    is also too heavy to pull for 5 years).
  * Fundamentals / valuation gate (Yahoo only gives today's snapshot).
  * Ranking inside the Top 20 uses the price-only part of the score
    (resilience + base), rescaled to 100.

Known biases, all flattering: the universe is *today's* Nifty 500 (names that
were delisted or dropped are missing -- survivorship), and today's large/mid
cap labels and sectors are applied to the past.

Entry is the close of the session AFTER the signal day; exit is H sessions
later. Returns are gross of costs, plus a net column at COST_ROUND_TRIP.
"""

import logging
from typing import Dict, List

import numpy as np
import pandas as pd

from .nse_data import fetch_cap_tiers, fetch_nifty500
from .resilience_strategy import (
    BENCHMARK, DMA200_SLOPE_MIN_PCT, DMA50_ENTRY_BAND, MIN_SIGNALS, MIN_TURNOVER_CR,
    OFF_HIGH_MAX_PCT, RANGE_40D_MAX_PCT,
)

logger = logging.getLogger(__name__)

PRICE_PERIOD = "5y"
REBALANCE_EVERY = 5          # sessions (weekly)
HORIZONS = (10, 20, 40)
WARMUP = 252                 # sessions before the first signal date (52-week high)
COST_ROUND_TRIP = 0.003
TOP_N, PER_SECTOR = 20, 3
CAP_PRIORITY = {"Large": 0, "Mid": 1}


def _scale(x, lo, hi, pts):
    return np.clip((x - lo) / (hi - lo), 0, 1) * pts


def compute_panels(close: pd.DataFrame, high: pd.DataFrame, volume: pd.DataFrame,
                   bench: pd.Series) -> Dict[str, pd.DataFrame]:
    """Every signal for every stock on every date, vectorised. Row t only
    ever uses data up to and including t."""
    b = bench.reindex(close.index).ffill()
    sma50, sma200 = close.rolling(50).mean(), close.rolling(200).mean()
    vs50 = (close / sma50 - 1) * 100
    slope200 = (sma200 / sma200.shift(20) - 1) * 100
    downtrend = (close < sma50) & (sma50 < sma200) & ((sma50 / sma50.shift(10) - 1) < 0)
    range40 = (close.rolling(40).max() / close.rolling(40).min() - 1) * 100
    off_high = (1 - close / high.rolling(252, min_periods=200).max()) * 100

    ret20, ret10 = close.pct_change(20) * 100, close.pct_change(10) * 100
    b20, b10 = b.pct_change(20) * 100, b.pct_change(10) * 100
    excess20, excess10 = ret20.sub(b20, axis=0), ret10.sub(b10, axis=0)

    r, br = close.pct_change(), b.pct_change()
    bench_down = (br < 0).astype(float)
    better_on_down = (r.gt(br, axis=0) & (br < 0).values[:, None]).astype(float)
    down_days = bench_down.rolling(40).sum()
    capture = better_on_down.rolling(40).sum().div(down_days.where(down_days >= 5), axis=0)
    vol_daily = r.rolling(40).std() * 100

    lo, hi = DMA50_ENTRY_BAND
    sig = {
        "beats_nifty": (excess20 >= 0) | (ret20 >= -2.0),
        "cushions_down_days": capture >= 0.5,
        "tight_base": range40 <= RANGE_40D_MAX_PCT,
        "near_50dma": (vs50 >= lo) & (vs50 <= hi),
        "ma200_flat_up": slope200 >= DMA200_SLOPE_MIN_PCT,
        "near_high": off_high <= OFF_HIGH_MAX_PCT,
        "not_downtrend": ~downtrend,
    }
    valid = sma200.notna() & slope200.notna() & off_high.notna() & range40.notna()
    signals = sum(v.fillna(False).astype(int) for v in sig.values()).where(valid)

    # Price-only part of the live score (resilience 40 + base 35), rescaled to 100.
    cap_fill = capture.fillna(0.4)
    score = (_scale(excess20, -2, 8, 17) + _scale(excess10, -2, 5, 8) + _scale(cap_fill, 0.4, 0.8, 15)
             + _scale(RANGE_40D_MAX_PCT * 2 - range40, 0, RANGE_40D_MAX_PCT * 2 - 8, 12)
             + _scale(6 - (vs50 + 0.5).abs(), 0, 6, 12) + _scale(slope200, -2, 1, 7)
             + _scale(OFF_HIGH_MAX_PCT * 1.5 - off_high, 0, OFF_HIGH_MAX_PCT * 1.5 - 5, 4)) / 75 * 100
    liquid = ((close * volume).rolling(20).mean() / 1e7) >= MIN_TURNOVER_CR
    market_weak = (b20 < 0) | (b < b.rolling(50).mean())
    return {"signals": signals, "score": score, "liquid": liquid, "weak": market_weak}


def select_top(sig_row: pd.Series, score_row: pd.Series, liquid_row: pd.Series,
               meta: pd.DataFrame) -> List[str]:
    cand = pd.DataFrame({"signals": sig_row, "score": score_row, "liquid": liquid_row}).join(meta)
    cand = cand[(cand["signals"] >= MIN_SIGNALS) & cand["liquid"] & cand["cap"].isin(CAP_PRIORITY)].copy()
    if cand.empty:
        return []
    cand["_cap"] = cand["cap"].map(CAP_PRIORITY)
    cand = cand.sort_values(["_cap", "signals", "score"], ascending=[True, False, False])
    cand = cand.groupby("industry", sort=False).head(PER_SECTOR)
    return cand.sort_values(["signals", "score"], ascending=False).head(TOP_N).index.tolist()


def run_backtest_resilience(period: str = PRICE_PERIOD) -> Dict:
    import yfinance as yf

    universe = fetch_nifty500()
    tiers = fetch_cap_tiers()
    meta = universe.set_index("Symbol")[["Industry"]].rename(columns={"Industry": "industry"})
    meta["cap"] = [tiers.get(s, "Small") for s in meta.index]

    tickers = [s + ".NS" for s in meta.index]
    data = yf.download(tickers, period=period, interval="1d", group_by="ticker",
                       auto_adjust=False, threads=True, progress=False)
    close = data.xs("Close", axis=1, level=1).dropna(axis=1, how="all")
    high = data.xs("High", axis=1, level=1)[close.columns]
    volume = data.xs("Volume", axis=1, level=1)[close.columns]
    for df in (close, high, volume):
        df.columns = [c.replace(".NS", "") for c in df.columns]
    bdf = yf.download(BENCHMARK, period=period, interval="1d", auto_adjust=False, progress=False)
    if isinstance(bdf.columns, pd.MultiIndex):
        bdf.columns = bdf.columns.get_level_values(0)
    bench = bdf["Close"].dropna()
    close = close[close.index.isin(bench.index)]
    high, volume = high.loc[close.index], volume.loc[close.index]
    meta = meta.loc[close.columns]

    panels = compute_panels(close, high, volume, bench)
    b = bench.reindex(close.index).ffill()
    n = len(close)
    max_h = max(HORIZONS)
    rows = []
    for i in range(WARMUP, n - 2 - max_h, REBALANCE_EVERY):
        d = close.index[i]
        sig_row, score_row, liq_row = panels["signals"].iloc[i], panels["score"].iloc[i], panels["liquid"].iloc[i]
        liquid_valid = liq_row & sig_row.notna()
        groups = {
            "All with >=3 signals": sig_row.index[(sig_row >= MIN_SIGNALS) & liquid_valid],
            "5+ signals": sig_row.index[(sig_row >= 5) & liquid_valid],
            "7 signals": sig_row.index[(sig_row >= 7) & liquid_valid],
            "Top 20 (<=3/sector, large then mid)": select_top(sig_row, score_row, liq_row, meta),
            "Universe (all liquid)": sig_row.index[liquid_valid],
        }
        for h in HORIZONS:
            entry, exit_ = close.iloc[i + 1], close.iloc[i + 1 + h]
            ret = (exit_ / entry - 1) * 100
            b_ret = (b.iloc[i + 1 + h] / b.iloc[i + 1] - 1) * 100
            for name, members in groups.items():
                r = ret.reindex(list(members)).dropna()
                if r.empty:
                    continue
                rows.append({"date": d, "group": name, "h": h, "n": len(r), "ret": r.mean(),
                             "bench": b_ret, "hit": (r > 0).mean() * 100,
                             "weak": bool(panels["weak"].iloc[i]),
                             "sig_ret": r, "members": list(r.index)})

    # Trade-level returns by signal count (20-session horizon).
    bucket_rows = []
    h = 20
    for i in range(WARMUP, n - 2 - h, REBALANCE_EVERY):
        sig_row, liq_row = panels["signals"].iloc[i], panels["liquid"].iloc[i]
        ret = (close.iloc[i + 1 + h] / close.iloc[i + 1] - 1) * 100
        universe_ret = ret[liq_row & sig_row.notna()].mean()
        df = pd.DataFrame({"signals": sig_row, "ret": ret})[liq_row & sig_row.notna()].dropna()
        df["excess_vs_universe"] = df["ret"] - universe_ret
        bucket_rows.append(df)
    buckets = pd.concat(bucket_rows)
    bucket_summary = buckets.groupby(buckets["signals"].astype(int)).agg(
        observations=("ret", "size"), mean_ret=("ret", "mean"),
        mean_excess_vs_universe=("excess_vs_universe", "mean"),
        hit_rate=("ret", lambda x: (x > 0).mean() * 100)).round(2)

    detail = pd.DataFrame(rows).drop(columns=["sig_ret", "members"])
    return {
        "detail": detail,
        "buckets": bucket_summary,
        "first_date": close.index[WARMUP].date().isoformat(),
        "last_date": close.index[n - 2 - max_h].date().isoformat(),
        "tickers": close.shape[1],
        "rebalances": detail[detail["h"] == 20]["date"].nunique(),
    }


def summarize(detail: pd.DataFrame) -> pd.DataFrame:
    out = []
    for (group, h), g in detail.groupby(["group", "h"]):
        uni = detail[(detail["group"] == "Universe (all liquid)") & (detail["h"] == h)].set_index("date")["ret"]
        excess_nifty = g["ret"] - g["bench"]
        excess_uni = g.set_index("date")["ret"] - uni.reindex(g["date"]).values
        out.append({
            "group": group, "horizon": h, "rebalances": len(g), "avg_picks": round(g["n"].mean(), 1),
            "mean_ret": g["ret"].mean(), "nifty_ret": g["bench"].mean(),
            "excess_vs_nifty": excess_nifty.mean(), "excess_vs_universe": excess_uni.mean(),
            "beat_nifty_%": (excess_nifty > 0).mean() * 100, "stock_hit_%": g["hit"].mean(),
            "net_ret": g["ret"].mean() - COST_ROUND_TRIP * 100,
            "excess_vs_nifty_weak_mkt": excess_nifty[g["weak"]].mean(),
            "excess_vs_nifty_strong_mkt": excess_nifty[~g["weak"]].mean(),
        })
    return pd.DataFrame(out).round(2)


def build_report(result: Dict) -> str:
    summ = summarize(result["detail"])
    d = result["detail"]
    weak_share = d[d["h"] == 20].drop_duplicates("date")["weak"].mean() * 100
    lines = [
        "# Resilience Screener Backtest", "",
        f"Signal dates {result['first_date']} to {result['last_date']}, {result['rebalances']} weekly rebalances, "
        f"{result['tickers']} current Nifty 500 names. Market flagged weak on {weak_share:.0f}% of signal dates. "
        "Entry = close of the session after the signal; equal weight; returns in %, gross unless marked net "
        f"(net = minus {COST_ROUND_TRIP * 100:.1f}% round trip).", "",
    ]
    for h in HORIZONS:
        lines += [f"## {h}-session holding period", "",
                  summ[summ["horizon"] == h].drop(columns="horizon").to_markdown(index=False), ""]
    lines += ["## Does a higher signal count help? (20-session, per stock)", "",
              result["buckets"].to_markdown(), "",
              "`mean_excess_vs_universe` = stock return minus the equal-weight average of all liquid stocks that day.", "",
              "## Read this with care", "",
              "- **Survivorship bias:** only stocks in today's Nifty 500 are tested; ones that fell out or delisted "
              "are missing, which flatters every row. Today's large/mid labels and sectors are applied to the past.",
              "- **Not tested:** delivery data, fundamentals and the valuation gate (no point-in-time data). "
              "The live Top 20 is also filtered by those, so this is the price-signal engine only.",
              "- **Overlap:** weekly rebalances with 10-40 session holds overlap, so the samples are not independent; "
              "treat small differences as noise.",
              "- One market cycle of ~5 years; nothing here is a guarantee. Not investment advice."]
    return "\n".join(lines) + "\n"
