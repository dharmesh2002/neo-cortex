"""
BSE.NS Pattern — 6-Month Historical Analysis
==============================================
1. Download BSE.NS for 6 months.
2. Find every day BSE.NS showed a bullish reversal pattern.
3. For each such day, find which other stocks also showed the same pattern.
4. Rank stocks by how often they co-occurred with BSE reversals.
5. Show next-day returns to see if the pattern actually worked.

Run in Google Colab:
  !pip install yfinance pandas tabulate -q
"""

# !pip install yfinance pandas tabulate -q

import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
import yfinance as yf
from collections import defaultdict

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 220)

TICKERS = [
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "KOTAKBANK.NS", "WIPRO.NS", "TATAMOTORS.NS", "SBIN.NS", "AXISBANK.NS",
    "ITC.NS", "LT.NS", "SUNPHARMA.NS", "MARUTI.NS", "BAJFINANCE.NS",
    "NTPC.NS", "POWERGRID.NS", "TITAN.NS", "ULTRACEMCO.NS", "ONGC.NS",
    "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS", "AUROPHARMA.NS",
    "HCLTECH.NS", "TECHM.NS", "MPHASIS.NS",
    "BAJAJFINSV.NS", "SHRIRAMFIN.NS", "CHOLAFIN.NS",
    "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS",
    "ASIANPAINT.NS", "BERGERPAINTS.NS",
    "DMART.NS", "TRENT.NS", "NYKAA.NS",
    "INDIGO.NS", "IRCTC.NS",
    "ADANIENT.NS", "ADANIPORTS.NS",
    "HDFCLIFE.NS", "SBILIFE.NS", "ICICIGI.NS",
    "PIDILITIND.NS", "ZOMATO.NS",
    "MCX.NS", "CDSL.NS", "CAMS.NS",
]

# ─────────────────────────────────────────────────────────────────────────────

def _rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_g = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_l = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_g / avg_l.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def _bb_lower(series, window=20, num_std=2.0):
    return series.rolling(window).mean() - num_std * series.rolling(window).std()

def _flatten(df):
    """Flatten MultiIndex columns from yfinance and normalise names."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns]
    df.columns = [str(c).strip().title() for c in df.columns]
    return df

def detect_patterns_series(df):
    """
    Run pattern detection on every row (not just the last).
    Returns a DataFrame indexed by date with one bool column per pattern.
    """
    df = _flatten(df)
    df = df.dropna(subset=["Open","High","Low","Close"]).copy()
    if len(df) < 30:
        return None

    c  = df["Close"]
    o  = df["Open"]
    h  = df["High"]
    l  = df["Low"]

    rng        = h - l
    body       = (c - o).abs()
    lower_wick = c.combine(o, min) - l
    upper_wick = h - c.combine(o, max)
    close_pos  = (c - l) / rng.replace(0, np.nan)

    rsi_s   = _rsi(c)
    bb_lo   = _bb_lower(c)
    support = l.rolling(120, min_periods=20).min()

    c1 = c.shift(1)
    o1 = o.shift(1)

    day_chg = (c - c1) / c1 * 100

    # Pattern A: Hammer
    hammer = (
        (rng > 0) & (body > 0)
        & (lower_wick >= 1.5 * body)
        & (lower_wick / rng >= 0.35)
        & (upper_wick / rng <= 0.30)
        & (close_pos >= 0.55)
    )

    # Pattern B: Bullish Engulfing
    bullish_engulfing = (
        (c1 < o1)           # prev candle red
        & (c > o)           # today green
        & (o <= c1)         # today open <= prev close
        & (c >= o1)         # today close >= prev open
    )

    # Pattern C: BB Lower Band Reversal
    bb_reversal = (
        (l <= bb_lo * 1.005)
        & (c > bb_lo)
        & (c > c1)
    )

    # Pattern D: Near Support
    near_support = ((c - support).abs() / support * 100 <= 2.0)

    # Pattern E: RSI Oversold Bounce
    rsi_bounce = (rsi_s <= 40) & (c > c1)

    result = pd.DataFrame({
        "close":             c,
        "day_chg%":          day_chg.round(2),
        "rsi14":             rsi_s.round(1),
        "bb_lower":          bb_lo.round(2),
        "hammer":            hammer,
        "bullish_engulfing": bullish_engulfing,
        "bb_reversal":       bb_reversal,
        "near_support":      near_support,
        "rsi_bounce":        rsi_bounce,
    }, index=df.index)

    # Any pattern fired
    pat_cols = ["hammer","bullish_engulfing","bb_reversal","near_support","rsi_bounce"]
    result["any_pattern"] = result[pat_cols].any(axis=1)
    result["pattern_count"] = result[pat_cols].sum(axis=1)

    # Next-day return (to measure outcome)
    result["next_day_ret%"] = c.shift(-1).sub(c).div(c).mul(100).round(2)

    return result

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Analyze BSE.NS over 6 months
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 65)
print("STEP 1 — BSE Ltd. (BSE.NS) — 6-month pattern history")
print("=" * 65)

bse_raw = yf.download("BSE.NS", period="6mo", interval="1d",
                      auto_adjust=True, progress=False)
bse_raw = _flatten(bse_raw).dropna(how="all")

bse = detect_patterns_series(bse_raw)
if bse is None:
    print("ERROR: Could not fetch BSE.NS")
    raise SystemExit

pat_cols = ["hammer","bullish_engulfing","bb_reversal","near_support","rsi_bounce"]

# Days where BSE.NS showed at least one pattern
bse_signal_days = bse[bse["any_pattern"]].copy()

print(f"\nTotal trading days in window: {len(bse)}")
print(f"Days with any reversal pattern: {len(bse_signal_days)}")
print(f"\nPattern frequency on BSE.NS:")
for pat in pat_cols:
    n = int(bse[pat].sum())
    pct = n / len(bse) * 100
    avg_ret = bse.loc[bse[pat], "next_day_ret%"].mean()
    print(f"  {pat:<22} {n:>3} days ({pct:.0f}%)   avg next-day return: {avg_ret:+.2f}%")

print(f"\nAll BSE.NS reversal days (last 6 months):\n")
show = bse_signal_days[["close","day_chg%","rsi14"] + pat_cols + ["pattern_count","next_day_ret%"]]
print(show.to_string())

print(f"\nBSE.NS reversal → next-day outcome:")
for pat in pat_cols:
    subset = bse.loc[bse[pat], "next_day_ret%"].dropna()
    if len(subset) == 0:
        continue
    wins = (subset > 0).sum()
    print(f"  {pat:<22}  {wins}/{len(subset)} profitable  "
          f"avg={subset.mean():+.2f}%  best={subset.max():+.2f}%  worst={subset.min():+.2f}%")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Same patterns across all stocks over 6 months
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print(f"STEP 2 — Scanning {len(TICKERS)} stocks for same patterns (6 months)")
print("=" * 65)
print("Downloading data...\n")

raw = yf.download(
    tickers=TICKERS, period="6mo", interval="1d",
    group_by="ticker", auto_adjust=True,
    threads=True, progress=False,
)

# For each ticker: how many times did each pattern fire, and what was the avg outcome
summary_rows = []
# Signal co-occurrence: on days BSE.NS had a pattern, did this stock too?
bse_signal_dates = set(bse_signal_days.index.date)

for ticker in TICKERS:
    try:
        df_t = raw[ticker].dropna(how="all")
        s = detect_patterns_series(df_t)
        if s is None:
            continue
    except Exception:
        continue

    row = {"ticker": ticker, "days": len(s)}

    for pat in pat_cols:
        n = int(s[pat].sum())
        subset = s.loc[s[pat], "next_day_ret%"].dropna()
        avg_ret = subset.mean() if len(subset) > 0 else np.nan
        wins = int((subset > 0).sum()) if len(subset) > 0 else 0
        row[f"{pat}_days"]    = n
        row[f"{pat}_avg_ret"] = round(avg_ret, 2) if not np.isnan(avg_ret) else None
        row[f"{pat}_win_pct"] = round(wins / len(subset) * 100) if len(subset) > 0 else None

    # Co-occurrence with BSE signal days
    stock_signal_dates = set(s[s["any_pattern"]].index.date)
    co_occur = len(bse_signal_dates & stock_signal_dates)
    row["co_occur_with_bse"] = co_occur
    row["co_occur_pct"]      = round(co_occur / len(bse_signal_dates) * 100) if bse_signal_dates else 0

    # Overall any_pattern stats
    row["total_signals"]  = int(s["any_pattern"].sum())
    all_ret = s.loc[s["any_pattern"], "next_day_ret%"].dropna()
    row["avg_next_ret%"]  = round(all_ret.mean(), 2) if len(all_ret) > 0 else None
    row["win_rate%"]      = round((all_ret > 0).sum() / len(all_ret) * 100) if len(all_ret) > 0 else None

    summary_rows.append(row)

df_sum = pd.DataFrame(summary_rows).sort_values("co_occur_with_bse", ascending=False)

# ── Overview table ──
print("\nStock summary — sorted by co-occurrence with BSE.NS reversal days:\n")
overview = df_sum[["ticker","total_signals","co_occur_with_bse","co_occur_pct","avg_next_ret%","win_rate%"]]
print(overview.to_string(index=False))

# ── Per-pattern breakdown ──
print(f"\n{'='*65}")
print("PATTERN BREAKDOWN — which pattern works best per stock\n")
for pat in pat_cols:
    cols = ["ticker", f"{pat}_days", f"{pat}_avg_ret", f"{pat}_win_pct"]
    sub = df_sum[cols].rename(columns={
        f"{pat}_days":    "days",
        f"{pat}_avg_ret": "avg_next_ret%",
        f"{pat}_win_pct": "win%",
    }).sort_values("avg_next_ret%", ascending=False).head(10)
    print(f"Top 10 stocks — {pat}:")
    print(sub.to_string(index=False))
    print()

# ── Best candidates: high co-occurrence + positive next-day return ──
print(f"{'='*65}")
print("BEST CANDIDATES — matches BSE pattern AND positive next-day returns\n")
best = df_sum[
    (df_sum["co_occur_pct"] >= 30) &
    (df_sum["avg_next_ret%"].notna()) &
    (df_sum["avg_next_ret%"] > 0) &
    (df_sum["win_rate%"].notna()) &
    (df_sum["win_rate%"] >= 50)
].sort_values(["co_occur_pct","avg_next_ret%"], ascending=[False,False])

if best.empty:
    print("No stock met all criteria — showing top 10 by co-occurrence:")
    best = df_sum.head(10)

print(best[["ticker","total_signals","co_occur_with_bse","co_occur_pct","avg_next_ret%","win_rate%"]].to_string(index=False))

print("\nDone.")
