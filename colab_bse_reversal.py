"""
BSE.NS Pattern Scanner
========================
Step 1: Analyze BSE Ltd. stock — find exactly what pattern it formed today.
Step 2: Scan all Nifty stocks for the SAME pattern.

Run in Google Colab:
  !pip install yfinance pandas tabulate -q
  # paste and run
"""

# !pip install yfinance pandas tabulate -q

import warnings; warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
import yfinance as yf

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)

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
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def _bb_lower(series, window=20, num_std=2.0):
    return series.rolling(window).mean() - num_std * series.rolling(window).std()

def detect_patterns(df):
    """Returns dict of all pattern flags + values for the latest candle."""
    df = df.dropna(subset=["Open","High","Low","Close"])
    if len(df) < 30:
        return None

    c  = float(df["Close"].iloc[-1])
    o  = float(df["Open"].iloc[-1])
    h  = float(df["High"].iloc[-1])
    l  = float(df["Low"].iloc[-1])
    c1 = float(df["Close"].iloc[-2])
    o1 = float(df["Open"].iloc[-2])
    h1 = float(df["High"].iloc[-2])
    l1 = float(df["Low"].iloc[-2])

    rng   = h - l
    body  = abs(c - o)
    lower_wick = min(c, o) - l
    upper_wick = h - max(c, o)
    close_pos  = (c - l) / rng if rng > 0 else 0.5   # 0=bottom, 1=top

    rsi_s   = _rsi(df["Close"])
    rsi_val = float(rsi_s.iloc[-1])
    rsi_1   = float(rsi_s.iloc[-2])

    bb_lo   = float(_bb_lower(df["Close"]).iloc[-1])
    support = float(df["Low"].rolling(min(120, len(df))).min().iloc[-1])

    day_chg = (c - c1) / c1 * 100

    # ── Pattern A: Hammer / Pin-bar ──
    # Long lower wick, closed in top half, green candle preferred
    hammer = bool(
        rng > 0 and body > 0
        and lower_wick >= 1.5 * body
        and lower_wick / rng >= 0.35
        and upper_wick / rng <= 0.30
        and close_pos >= 0.55
    )

    # ── Pattern B: Bullish Engulfing ──
    prev_red   = c1 < o1
    today_green = c > o
    engulfs    = o <= c1 and c >= o1
    bullish_engulfing = bool(prev_red and today_green and engulfs)

    # ── Pattern C: Bollinger Lower Band Reversal ──
    bb_reversal = bool(
        l <= bb_lo * 1.005
        and c > bb_lo
        and c > c1
    )

    # ── Pattern D: Support Bounce ──
    near_support = bool(abs(c - support) / support * 100 <= 2.0)

    # ── Pattern E: RSI Oversold Bounce ──
    rsi_bounce = bool(rsi_val <= 40 and (c > c1 or rsi_val <= 30))

    return {
        "close": c, "open": o, "high": h, "low": l,
        "day_chg%": round(day_chg, 2),
        "rsi14": round(rsi_val, 1),
        "bb_lower": round(bb_lo, 2),
        "support": round(support, 2),
        "lower_wick%": round(lower_wick / c * 100, 2) if c > 0 else 0,
        "body%": round(body / c * 100, 2) if c > 0 else 0,
        "close_pos%": round(close_pos * 100, 1),
        "hammer":             hammer,
        "bullish_engulfing":  bullish_engulfing,
        "bb_reversal":        bb_reversal,
        "near_support":       near_support,
        "rsi_bounce":         rsi_bounce,
    }

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Analyze BSE.NS — find the pattern
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 65)
print("STEP 1 — Analyzing BSE Ltd. (BSE.NS)")
print("=" * 65)

bse_df = yf.download("BSE.NS", period="6mo", interval="1d",
                     auto_adjust=True, progress=False)
bse_df = bse_df.dropna(how="all")

if len(bse_df) < 30:
    print("ERROR: Could not fetch BSE.NS data. Check internet connection.")
else:
    p = detect_patterns(bse_df)

    print(f"\nBSE Ltd. — last 5 days:")
    print(bse_df[["Open","High","Low","Close"]].tail(5).round(2).to_string())

    print(f"\nToday's candle:")
    print(f"  Open:       {p['open']:>10,.2f}")
    print(f"  High:       {p['high']:>10,.2f}")
    print(f"  Low:        {p['low']:>10,.2f}")
    print(f"  Close:      {p['close']:>10,.2f}   ({p['day_chg%']:+.2f}%)")
    print(f"  RSI(14):    {p['rsi14']}")
    print(f"  BB lower:   {p['bb_lower']:>10,.2f}")
    print(f"  Support:    {p['support']:>10,.2f}")
    print(f"  Lower wick: {p['lower_wick%']:.2f}% of price")
    print(f"  Body:       {p['body%']:.2f}% of price")
    print(f"  Close pos:  {p['close_pos%']:.0f}% of day's range (100=at high)")

    print(f"\nPatterns fired on BSE.NS today:")
    bse_patterns = {}
    for pat in ["hammer","bullish_engulfing","bb_reversal","near_support","rsi_bounce"]:
        fired = p[pat]
        bse_patterns[pat] = fired
        label = {
            "hammer":            "Hammer / Pin-bar",
            "bullish_engulfing": "Bullish Engulfing",
            "bb_reversal":       "BB Lower Band Reversal",
            "near_support":      "Near Horizontal Support",
            "rsi_bounce":        "RSI Oversold Bounce",
        }[pat]
        print(f"  {'✓' if fired else '✗'}  {label}")

    active_patterns = [p for p, v in bse_patterns.items() if v]
    print(f"\n→ {len(active_patterns)} pattern(s) fired: {', '.join(active_patterns) if active_patterns else 'none'}")

    if not active_patterns:
        print("\nNo standard reversal pattern detected on BSE.NS today.")
        print("Check if today was actually a down day or flat day for BSE stock.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: Find same patterns in all Nifty stocks
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 65)
print(f"STEP 2 — Scanning {len(TICKERS)} stocks for same pattern(s)")
print("=" * 65)
print(f"Looking for: {', '.join(active_patterns) if active_patterns else 'all patterns'}\n")

print(f"Downloading data...")
raw = yf.download(
    tickers=TICKERS, period="6mo", interval="1d",
    group_by="ticker", auto_adjust=True,
    threads=True, progress=False,
)

rows = []
for ticker in TICKERS:
    try:
        df_t = raw[ticker].dropna(how="all")
        r = detect_patterns(df_t)
        if r is None:
            continue
        # Count how many of BSE's patterns this stock also shows
        if active_patterns:
            match_count = sum(r[pat] for pat in active_patterns)
        else:
            match_count = sum([r["hammer"], r["bullish_engulfing"],
                               r["bb_reversal"], r["near_support"], r["rsi_bounce"]])
        r["ticker"] = ticker
        r["bse_pattern_match"] = match_count
        rows.append(r)
    except Exception:
        continue

if not rows:
    print("No data returned.")
else:
    df_out = pd.DataFrame(rows).sort_values(
        ["bse_pattern_match", "day_chg%"], ascending=[False, False]
    ).reset_index(drop=True)

    display_cols = ["ticker","close","day_chg%","rsi14",
                    "hammer","bullish_engulfing","bb_reversal","near_support","rsi_bounce",
                    "bse_pattern_match"]

    print(f"\nAll {len(df_out)} stocks (sorted by pattern match):\n")
    print(df_out[display_cols].to_string(index=False))

    # Stocks showing the same pattern as BSE.NS
    if active_patterns:
        full_match = df_out[df_out["bse_pattern_match"] == len(active_patterns)]
        partial    = df_out[df_out["bse_pattern_match"] == max(1, len(active_patterns) - 1)]

        print(f"\n{'='*65}")
        print(f"EXACT MATCH — same {len(active_patterns)} pattern(s) as BSE.NS: {len(full_match)} stocks")
        if full_match.empty:
            print("  None today")
        else:
            print(full_match[display_cols].to_string(index=False))

        if len(active_patterns) > 1:
            print(f"\nNEAR MATCH — {len(active_patterns)-1}/{len(active_patterns)} patterns: {len(partial)} stocks")
            if partial.empty:
                print("  None today")
            else:
                print(partial[display_cols].to_string(index=False))

print("\nDone.")
