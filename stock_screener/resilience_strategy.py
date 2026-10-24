"""Resilience + Accumulation screener.

Looks for stocks that hold up while the market is weak AND show delivery-
backed accumulation, sitting in a base near their 50-day average:

1. Resilience  -- the benchmark (Nifty 50) is weak, the stock falls less
   than it, holds its range, or rises.
2. Delivery    -- 5-day average delivery quantity >= 1.25x the 60-day
   average (1.5x+ is the strong tier), cross-checked against delivery %
   and total traded quantity so a plain turnover spike doesn't pass.
3. Base/trend  -- tight 40-day range, close near the 50-day average, a
   200-day average that is flat or rising, not far off the 52-week high.
4. Fundamentals + valuation -- only for names that clear 1-3: quality gate
   (ROE, debt, FCF, growth) and >= 25% upside to a conservative intrinsic
   value (Graham number, sqrt(22.5 x EPS x book value per share)).

Each stock also gets a 100-point score. The first-pass rule from the
original screenshots (looser thresholds) is evaluated alongside so the two
can be reconciled name by name.

Delivery data comes from NSE's bhavcopy archive; prices from Yahoo Finance.
"""

import logging
import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .nse_data import delivery_series_by_symbol, fetch_cap_tiers, fetch_delivery_history, fetch_nifty500
from .pullback_strategy import fetch_fundamentals

logger = logging.getLogger(__name__)

PRICE_PERIOD = "2y"
MIN_HISTORY_ROWS = 220  # 200-day average plus its 20-day slope lookback
BENCHMARK = "^NSEI"

# --- Proposed (strict) rules -------------------------------------------------
# Delivery is information only: it is reported (quantity ratio, delivery %
# change in points) but takes no part in the gate or the score.
RANGE_40D_MAX_PCT = 12.0
DMA50_ENTRY_BAND = (-3.0, 5.0)       # % vs 50-day for an entry-test pass
MIN_SIGNALS = 3                      # of 7 price signals needed to be a candidate
MAX_SIGNALS = 7
OFF_HIGH_MAX_PCT = 20.0
DMA200_SLOPE_MIN_PCT = -1.0          # 200-day today vs 20 sessions ago: "flat or rising"
MIN_TURNOVER_CR = 5.0
STRONG_TURNOVER_CR = 20.0
MIN_UPSIDE_PCT = 25.0

# --- First-pass rules (as in the original screenshot) -------------------------
LEGACY_DELIVERY_RATIO_MIN = 1.15
LEGACY_DMA50_MIN = -3.0              # within 3% below the 50-day, or above it
LEGACY_OFF_HIGH_MAX_PCT = 20.0

# Names from the original screenshot, reconciled against the new rules in the report.
SCREENSHOT_NAMES = ["AXISBANK", "ICICIBANK", "INDHOTEL", "SUPREMEIND", "PHOENIXLTD",
                    "HCLTECH", "MPHASIS", "PETRONET", "ITC", "ASIANPAINT"]

FINANCIAL_SECTORS = {"financial services", "financials"}
# Nifty 500 CSV's own "Industry" column, used when Yahoo has no sector.
FINANCIAL_INDUSTRIES = {"financial services"}


# ---------------------------------------------------------------------------
# Technical building blocks
# ---------------------------------------------------------------------------
def classify_trend(close: pd.Series) -> str:
    """Uptrend / Downtrend / Sideways (base) / No clear trend / Can't judge.

    Sideways means a narrow 40-day range with the close hugging the 50-day;
    Uptrend/Downtrend need price, 50-day and 200-day stacked in order with
    the 50-day moving the same way.
    """
    if len(close.dropna()) < MIN_HISTORY_ROWS:
        return "Can't judge"
    sma50, sma200 = close.rolling(50).mean(), close.rolling(200).mean()
    c, s50, s200 = close.iloc[-1], sma50.iloc[-1], sma200.iloc[-1]
    s50_slope = s50 / sma50.iloc[-11] - 1
    last40 = close.iloc[-40:]
    range40 = (last40.max() / last40.min() - 1) * 100
    if c > s50 > s200 and s50_slope > 0:
        return "Uptrend"
    if c < s50 < s200 and s50_slope < 0:
        return "Downtrend"
    if range40 <= 15 and abs(c / s50 - 1) <= 0.05:
        return "Sideways (base)"
    return "No clear trend"


def _ret(close: pd.Series, n: int) -> float:
    return float((close.iloc[-1] / close.iloc[-1 - n] - 1) * 100)


def downside_capture(stock: pd.Series, bench: pd.Series, window: int = 40) -> Optional[float]:
    """Share of the benchmark's down days (last `window` sessions) on which
    the stock did better than the benchmark. 1.0 = always cushioned."""
    joined = pd.concat([stock.pct_change(), bench.pct_change()], axis=1, keys=["s", "b"]).dropna().iloc[-window:]
    down = joined[joined["b"] < 0]
    if len(down) < 5:
        return None
    return float((down["s"] > down["b"]).mean())


def delivery_metrics(d: pd.DataFrame) -> Optional[Dict]:
    """d: one symbol's bhavcopy rows indexed by Date (ascending)."""
    d = d.dropna(subset=["DELIV_QTY"])
    if len(d) < 60:
        return None
    last60, last5 = d.iloc[-60:], d.iloc[-5:]
    base_qty = last60["DELIV_QTY"].mean()
    if not base_qty:
        return None
    base_total = last60["TTL_TRD_QNTY"].mean()
    return {
        "deliv_ratio": float(last5["DELIV_QTY"].mean() / base_qty),
        "deliv_pct_5d": float(last5["DELIV_PER"].mean()),
        "deliv_pct_60d": float(last60["DELIV_PER"].mean()),
        "total_vol_ratio": float(last5["TTL_TRD_QNTY"].mean() / base_total) if base_total else float("nan"),
        "turnover_cr_20d": float(d.iloc[-20:]["TURNOVER_LACS"].mean() / 100),  # lakh -> crore
    }


def evaluate_technicals(df: pd.DataFrame, bench_close: pd.Series) -> Optional[Dict]:
    df = df.dropna(subset=["Close"])
    close = df["Close"]
    if len(close) < MIN_HISTORY_ROWS:
        return None
    sma20, sma50, sma200 = close.rolling(20).mean(), close.rolling(50).mean(), close.rolling(200).mean()
    vol = df["Volume"].dropna() if "Volume" in df else pd.Series(dtype=float)
    vol_today = float(vol.iloc[-1]) if len(vol) else float("nan")
    vol_prev = float(vol.iloc[-2]) if len(vol) > 1 else float("nan")
    vol_avg20 = float(vol.iloc[-21:-1].mean()) if len(vol) > 20 else float("nan")
    last40 = close.iloc[-40:]
    last20 = close.iloc[-20:]
    high_252 = df["High"].iloc[-252:].max() if "High" in df else close.iloc[-252:].max()
    returns = close.pct_change().iloc[-40:]
    bench_aligned = bench_close.reindex(close.index).ffill()

    return {
        "close": float(close.iloc[-1]),
        "day_pct": float((close.iloc[-1] / close.iloc[-2] - 1) * 100),
        "dma20": float(sma20.iloc[-1]),
        "dma50": float(sma50.iloc[-1]),
        "dma200": float(sma200.iloc[-1]),
        "vs_20dma_pct": float((close.iloc[-1] / sma20.iloc[-1] - 1) * 100),
        "volume": vol_today,
        "vol_chg_pct": (vol_today / vol_prev - 1) * 100 if vol_prev else float("nan"),
        "vol_vs_20d_pct": (vol_today / vol_avg20 - 1) * 100 if vol_avg20 else float("nan"),
        "trend": classify_trend(close),
        "vs_50dma_pct": float((close.iloc[-1] / sma50.iloc[-1] - 1) * 100),
        "vs_200dma_pct": float((close.iloc[-1] / sma200.iloc[-1] - 1) * 100),
        "dma200_slope_pct": float((sma200.iloc[-1] / sma200.iloc[-21] - 1) * 100),
        "off_high_pct": float((1 - close.iloc[-1] / high_252) * 100),
        "range_40d_pct": float((last40.max() / last40.min() - 1) * 100),
        "range_20d_pct": float((last20.max() / last20.min() - 1) * 100),
        "ret_20d_pct": _ret(close, 20),
        "ret_10d_pct": _ret(close, 10),
        "excess_20d_pct": _ret(close, 20) - _ret(bench_aligned.dropna(), 20),
        "excess_10d_pct": _ret(close, 10) - _ret(bench_aligned.dropna(), 10),
        "downside_capture": downside_capture(close, bench_aligned),
        "daily_vol_pct": float(returns.std() * 100),
    }


def market_context(bench_df: pd.DataFrame) -> Dict:
    close = bench_df["Close"].dropna()
    sma50 = close.rolling(50).mean()
    ctx = {
        "trend": classify_trend(close),
        "close": float(close.iloc[-1]),
        "ret_20d_pct": _ret(close, 20),
        "ret_5d_pct": _ret(close, 5),
        "vs_50dma_pct": float((close.iloc[-1] / sma50.iloc[-1] - 1) * 100),
        "as_of": close.index[-1].date().isoformat(),
    }
    ctx["weak"] = bool(ctx["ret_20d_pct"] < 0 or ctx["vs_50dma_pct"] < 0)
    return ctx


# ---------------------------------------------------------------------------
# Rule sets
# ---------------------------------------------------------------------------
def legacy_screen(t: Dict, dlv: Dict) -> Dict:
    """The first-pass 'strongest candidates' rule from the original screenshot
    (valuation 'not historically expensive' is not reproducible from public
    data and is replaced by the explicit valuation gate in the new rules)."""
    checks = {
        "trend_ok": t["trend"] in {"Uptrend", "Sideways (base)", "No clear trend"},
        "near_50dma": t["vs_50dma_pct"] >= LEGACY_DMA50_MIN,
        "off_high_ok": t["off_high_pct"] <= LEGACY_OFF_HIGH_MAX_PCT,
        "delivery_qty_ok": dlv["deliv_ratio"] >= LEGACY_DELIVERY_RATIO_MIN,
        "delivery_pct_ok": dlv["deliv_pct_5d"] >= dlv["deliv_pct_60d"],
        "liquid": dlv["turnover_cr_20d"] >= MIN_TURNOVER_CR,
    }
    return {"legacy_pass": all(checks.values()),
            "legacy_failed": ", ".join(k for k, v in checks.items() if not v)}


def strict_screen(t: Dict, dlv: Dict, market_weak: bool) -> Dict:
    """Count how many price signals a stock shows. No single signal is
    mandatory: MIN_SIGNALS of them make it a candidate. Liquidity is the only
    hard requirement (an untradeable name is no candidate however it looks)."""
    lo, hi = DMA50_ENTRY_BAND
    # Delivery quantity rising no faster than total volume means the surge may
    # just be more turnover, not more holding -- flagged only.
    turnover_driven = bool(not math.isnan(dlv["total_vol_ratio"]) and dlv["deliv_ratio"] <= dlv["total_vol_ratio"])
    capture = t["downside_capture"]

    signals = {
        "beats_nifty": t["excess_20d_pct"] >= 0 or t["ret_20d_pct"] >= -2.0,
        "cushions_down_days": bool(capture is not None and capture >= 0.5),
        "tight_base": t["range_40d_pct"] <= RANGE_40D_MAX_PCT,
        "near_50dma": lo <= t["vs_50dma_pct"] <= hi,
        "ma200_flat_up": t["dma200_slope_pct"] >= DMA200_SLOPE_MIN_PCT,
        "near_high": t["off_high_pct"] <= OFF_HIGH_MAX_PCT,
        "not_downtrend": t["trend"] != "Downtrend",
    }
    n = sum(signals.values())
    liquid = dlv["turnover_cr_20d"] >= MIN_TURNOVER_CR
    return {
        "signals": n,
        "signals_passed": ", ".join(k for k, v in signals.items() if v),
        "technical_failed": ", ".join(k for k, v in signals.items() if not v),
        "technical_pass": bool(n >= MIN_SIGNALS and liquid),
        "turnover_driven": turnover_driven,
        "deliv_pct_chg_pts": dlv["deliv_pct_5d"] - dlv["deliv_pct_60d"],
        "market_weak": market_weak,
    }


# ---------------------------------------------------------------------------
# Fundamentals + valuation
# ---------------------------------------------------------------------------
def graham_value(info: Dict) -> Optional[float]:
    eps, bvps = info.get("trailingEps"), info.get("bookValue")
    if eps is None or bvps is None or eps <= 0 or bvps <= 0:
        return None
    return float(math.sqrt(22.5 * eps * bvps))


def fundamentals_gate(info: Dict, close: float, financial: bool) -> Dict:
    roe = info.get("returnOnEquity")
    dte = info.get("debtToEquity")
    fcf = info.get("freeCashflow")
    eg, rg = info.get("earningsGrowth"), info.get("revenueGrowth")
    rec = (info.get("recommendationKey") or "").lower()

    checks = {
        "roe_ok": bool(roe is not None and roe > 0.15),
        "debt_ok": financial or bool(dte is not None and dte < 100),
        "fcf_ok": financial or bool(fcf is not None and fcf > 0),   # FCF is not meaningful for lenders
        "earnings_outlook_ok": bool((eg is not None and eg > 0) or (rg is not None and rg > 0)),
        "analyst_ok": rec not in {"sell", "underperform", "strong_sell"},
    }
    iv = graham_value(info)
    upside = (iv / close - 1) * 100 if iv else None
    return {
        **checks,
        "fundamentals_pass": all(checks.values()),
        "roe_pct": roe * 100 if roe is not None else None,
        "debt_to_equity": dte,
        "intrinsic_value": iv,
        "upside_pct": upside,
        "valuation_pass": bool(upside is not None and upside >= MIN_UPSIDE_PCT),
        "pe": info.get("trailingPE"),
        "sector": info.get("sector", ""),
    }


# ---------------------------------------------------------------------------
# 100-point score
# ---------------------------------------------------------------------------
def _scale(x: float, lo: float, hi: float, pts: float) -> float:
    if hi == lo:
        return 0.0
    return float(np.clip((x - lo) / (hi - lo), 0, 1) * pts)


def score_stock(t: Dict, dlv: Dict, f: Optional[Dict]) -> Dict:
    # Price-only technical score. Resilience vs the market: 40
    rs = _scale(t["excess_20d_pct"], -2, 8, 17)
    rs += _scale(t["excess_10d_pct"], -2, 5, 8)
    capture = t["downside_capture"]
    rs += _scale(capture if capture is not None else 0.4, 0.4, 0.8, 15)

    # Base quality and moving averages: 35
    base = _scale(RANGE_40D_MAX_PCT * 2 - t["range_40d_pct"], 0, RANGE_40D_MAX_PCT * 2 - 8, 12)
    base += _scale(6 - abs(t["vs_50dma_pct"] + 0.5), 0, 6, 12)
    base += _scale(t["dma200_slope_pct"], -2, 1, 7)
    base += _scale(OFF_HIGH_MAX_PCT * 1.5 - t["off_high_pct"], 0, OFF_HIGH_MAX_PCT * 1.5 - 5, 4)

    # Fundamental quality: 12 / valuation: 8 (only known once fundamentals were fetched)
    fund = val = 0.0
    if f:
        fund = 3 * f["roe_ok"] + 3 * f["debt_ok"] + 3 * f["fcf_ok"] + 3 * f["earnings_outlook_ok"]
        val = _scale(f["upside_pct"], 0, MIN_UPSIDE_PCT, 8) if f["upside_pct"] is not None else 0.0

    # Liquidity and risk controls: 5
    liq = _scale(dlv["turnover_cr_20d"], MIN_TURNOVER_CR, STRONG_TURNOVER_CR, 2)
    liq += _scale(3.0 - t["daily_vol_pct"], 0, 1.5, 3)

    parts = {"s_resilience": rs, "s_base": base,
             "s_fundamental": fund, "s_valuation": val, "s_liquidity": liq}
    parts = {k: round(float(v), 1) for k, v in parts.items()}
    parts["score"] = round(sum(parts.values()), 1)
    return parts


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def classify(row: Dict) -> str:
    if row["technical_pass"] and row.get("fundamentals_pass") and row.get("valuation_pass"):
        return "Potential buy"
    if row["technical_pass"] and row.get("fundamentals_pass"):
        return "Priority watch"
    if row["technical_pass"]:
        return "Candidate"
    return ""


def run_resilience_screen(info_sleep_seconds: float = 0.3, universe: Optional[pd.DataFrame] = None,
                          extra_symbols: Optional[List[str]] = None) -> Dict:
    import yfinance as yf

    universe = universe if universe is not None else fetch_nifty500()
    symbols = universe["Symbol"].tolist()
    for s in extra_symbols or []:
        if s not in symbols:
            symbols.append(s)
    tickers = [s + ".NS" for s in symbols]
    industry = dict(zip(universe["Symbol"], universe.get("Industry", "")))
    company = dict(zip(universe["Symbol"], universe.get("Company Name", universe["Symbol"])))

    cap_tier = fetch_cap_tiers()  # Nifty 100 = Large, Midcap 150 = Mid, everything else Small
    delivery = delivery_series_by_symbol(fetch_delivery_history(trading_days=66))
    delivery_asof = max(df.index.max() for df in delivery.values()).date().isoformat()

    bench_df = yf.download(BENCHMARK, period=PRICE_PERIOD, interval="1d", auto_adjust=False, progress=False)
    if isinstance(bench_df.columns, pd.MultiIndex):
        bench_df.columns = bench_df.columns.get_level_values(0)
    ctx = market_context(bench_df)
    bench_close = bench_df["Close"].dropna()

    data = yf.download(tickers, period=PRICE_PERIOD, interval="1d", group_by="ticker",
                       auto_adjust=False, threads=True, progress=False)

    rows: List[Dict] = []
    skipped = {"no_prices": 0, "no_delivery": 0}
    for sym in symbols:
        try:
            px = data[sym + ".NS"].dropna(how="all")
        except KeyError:
            skipped["no_prices"] += 1
            continue
        t = evaluate_technicals(px, bench_close)
        if t is None:
            skipped["no_prices"] += 1
            continue
        dlv = delivery_metrics(delivery[sym]) if sym in delivery else None
        if dlv is None:
            skipped["no_delivery"] += 1
            continue
        row = {"ticker": sym, "company": company.get(sym, sym), "industry": industry.get(sym, ""),
               "cap": cap_tier.get(sym, "Small"),
               **t, **dlv, **legacy_screen(t, dlv), **strict_screen(t, dlv, ctx["weak"])}
        rows.append(row)

    # Fundamentals only for names that clear the technical bar (slow per-ticker call).
    for row in rows:
        if not row["technical_pass"]:
            continue
        info = fetch_fundamentals(row["ticker"] + ".NS", info_sleep_seconds)
        financial = (info.get("sector", "").lower() in FINANCIAL_SECTORS
                     or row["industry"].lower() in FINANCIAL_INDUSTRIES)
        row.update(fundamentals_gate(info, row["close"], financial))

    for row in rows:
        f = row if "fundamentals_pass" in row else None
        row.update(score_stock(row, row, f))
        row["verdict"] = classify(row)

    rows.sort(key=lambda r: (r["signals"], r["score"]), reverse=True)
    trend_counts = pd.Series([r["trend"] for r in rows]).value_counts().to_dict()
    return {
        "rows": rows,
        "context": ctx,
        "delivery_asof": delivery_asof,
        "universe_size": len(symbols),
        "evaluated": len(rows),
        "skipped": skipped,
        "trend_counts": trend_counts,
    }
