"""
BSE / Nifty Bullish Reversal Scanner
=====================================
Run in Google Colab:
  !pip install yfinance pandas tabulate -q
  # paste this script and run

Detects the same reversal pattern BSE Sensex / Nifty showed today:
  - Hammer / Pin-bar candle  (long lower wick, closed near top)
  - Bollinger lower band touch + recovery
  - Near horizontal support bounce
  - RSI oversold bounce (RSI crossed up through 35 or still <= 38)

Scores each ticker 0-4 and ranks by reversal strength.
"""

# ── Install if needed ──────────────────────────────────────────────────────────
# !pip install yfinance pandas tabulate -q

import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
import yfinance as yf

pd.set_option("display.max_columns", None)
pd.set_option("display.width", 220)
pd.set_option("display.float_format", lambda x: f"{x:.2f}")

# ── Tickers ────────────────────────────────────────────────────────────────────
# Indices to check first (^BSESN = Sensex, ^NSEI = Nifty 50)
INDEX_TICKERS = ["^BSESN", "^NSEI"]

STOCK_TICKERS = [
    # Large cap
    "RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS",
    "KOTAKBANK.NS", "WIPRO.NS", "TATAMOTORS.NS", "SBIN.NS", "AXISBANK.NS",
    "ITC.NS", "LT.NS", "SUNPHARMA.NS", "MARUTI.NS", "BAJFINANCE.NS",
    "NTPC.NS", "POWERGRID.NS", "TITAN.NS", "ULTRACEMCO.NS", "ONGC.NS",
    # Midcap / sectoral
    "CIPLA.NS", "DRREDDY.NS", "DIVISLAB.NS", "AUROPHARMA.NS",
    "HCLTECH.NS", "TECHM.NS", "MPHASIS.NS",
    "BAJAJFINSV.NS", "SHRIRAMFIN.NS", "CHOLAFIN.NS",
    "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS",
    "ASIANPAINT.NS", "BERGERPAINTS.NS",
    "DMART.NS", "TRENT.NS", "NYKAA.NS",
    "INDIGO.NS", "IRCTC.NS",
    "ADANIENT.NS", "ADANIPORTS.NS", "ADANIPOWER.NS",
    "HDFCLIFE.NS", "SBILIFE.NS", "ICICIGI.NS",
    "PIDILITIND.NS", "BALKRISIND.NS",
    "ZOMATO.NS", "PAYTM.NS", "POLICYBZR.NS",
]

# ── Helpers ────────────────────────────────────────────────────────────────────

def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def _bollinger(series: pd.Series, window: int = 20, num_std: float = 2.0):
    mid = series.rolling(window).mean()
    std = series.rolling(window).std()
    return mid - num_std * std, mid, mid + num_std * std


def analyze_reversal(df: pd.DataFrame, ticker: str) -> dict | None:
    """Return reversal metrics for the latest candle."""
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    if len(df) < 30:
        return None

    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    open_ = df["Open"]

    rsi_s = _rsi(close)
    bb_lower, bb_mid, bb_upper = _bollinger(close)

    # ── Latest candle values ──
    c  = float(close.iloc[-1])
    o  = float(open_.iloc[-1])
    h  = float(high.iloc[-1])
    l  = float(low.iloc[-1])
    c_prev = float(close.iloc[-2])
    o_prev = float(open_.iloc[-2])

    rsi_val      = float(rsi_s.iloc[-1])
    rsi_prev     = float(rsi_s.iloc[-2])
    bb_lo        = float(bb_lower.iloc[-1])
    bb_lo_prev   = float(bb_lower.iloc[-2])

    # Day change %
    day_chg = (c - c_prev) / c_prev * 100

    # ── Pattern 1: Hammer / Pin-bar ──────────────────────────────────────────
    # Candle range
    candle_range = h - l
    body = abs(c - o)
    lower_wick = min(c, o) - l          # how far price fell below the body
    upper_wick = h - max(c, o)

    # Hammer: lower wick >= 2x body, closed in upper 40% of range, range > 0
    hammer = False
    if candle_range > 0 and body > 0:
        lower_wick_ratio = lower_wick / candle_range
        upper_wick_ratio = upper_wick / candle_range
        close_position   = (c - l) / candle_range   # 0 = bottom, 1 = top
        hammer = (
            lower_wick >= 2 * body          # long lower wick
            and lower_wick_ratio >= 0.40    # wick is at least 40% of range
            and upper_wick_ratio <= 0.25    # small upper wick
            and close_position >= 0.60      # closed in upper 40% of day's range
        )

    # ── Pattern 2: BB lower band touch + recovery ────────────────────────────
    bb_reversal = bool(
        l <= bb_lo * 1.005           # low touched or came within 0.5% of lower band
        and c > bb_lo                # but closed above lower band
        and c > c_prev               # and closed higher than yesterday
    )

    # ── Pattern 3: Near horizontal support (120-day rolling low) ─────────────
    support_lookback = min(120, len(df))
    horizontal_support = float(low.iloc[-support_lookback:].min())
    near_support = abs(c - horizontal_support) / horizontal_support * 100 <= 2.0

    # ── Pattern 4: RSI oversold bounce ───────────────────────────────────────
    # RSI was oversold and is starting to turn, or just recovered above 30
    rsi_bounce = bool(
        rsi_val <= 38                # still low
        and (rsi_val > rsi_prev or rsi_val <= 35)  # turning up or deeply oversold
    )

    score = sum([hammer, bb_reversal, near_support, rsi_bounce])

    return {
        "ticker":       ticker,
        "close":        round(c, 2),
        "day_chg%":     round(day_chg, 2),
        "rsi14":        round(rsi_val, 1),
        "bb_lower":     round(bb_lo, 2),
        "support":      round(horizontal_support, 2),
        "hammer":       hammer,
        "bb_reversal":  bb_reversal,
        "near_support": near_support,
        "rsi_bounce":   rsi_bounce,
        "score":        score,
        "lower_wick%":  round(lower_wick / c * 100, 2) if c > 0 else 0,
        "body%":        round(body / c * 100, 2) if c > 0 else 0,
    }


# ── Step 1: What did BSE / Nifty do today? ────────────────────────────────────
print("=" * 60)
print("STEP 1 — BSE Sensex & Nifty 50 today's candle pattern")
print("=" * 60)

idx_raw = yf.download(
    tickers=INDEX_TICKERS,
    period="60d", interval="1d",
    group_by="ticker", auto_adjust=True,
    threads=True, progress=False,
)

for t in INDEX_TICKERS:
    try:
        df_idx = idx_raw[t].dropna(how="all") if len(INDEX_TICKERS) > 1 else idx_raw.dropna(how="all")
        r = analyze_reversal(df_idx, t)
        if r is None:
            print(f"{t}: not enough data")
            continue

        label = "BSE Sensex" if t == "^BSESN" else "Nifty 50"
        c, o = float(df_idx["Close"].iloc[-1]), float(df_idx["Open"].iloc[-1])
        h_val, l_val = float(df_idx["High"].iloc[-1]), float(df_idx["Low"].iloc[-1])

        print(f"\n{label} ({t})")
        print(f"  Open:  {o:>10,.2f}   High:  {h_val:>10,.2f}")
        print(f"  Low:   {l_val:>10,.2f}   Close: {c:>10,.2f}   Change: {r['day_chg%']:+.2f}%")
        print(f"  RSI14: {r['rsi14']:.1f}   BB_lower: {r['bb_lower']:,.2f}")
        print(f"  Lower wick: {r['lower_wick%']:.2f}% of close   Body: {r['body%']:.2f}% of close")
        print(f"  Patterns detected:")
        print(f"    Hammer/Pin-bar:      {'YES ✓' if r['hammer'] else 'no'}")
        print(f"    BB lower reversal:   {'YES ✓' if r['bb_reversal'] else 'no'}")
        print(f"    Near support:        {'YES ✓' if r['near_support'] else 'no'}")
        print(f"    RSI oversold bounce: {'YES ✓' if r['rsi_bounce'] else 'no'}")
        print(f"  Reversal score: {r['score']}/4")

        # Interpretation
        if r["hammer"]:
            print(f"\n  *** HAMMER CANDLE: Index fell hard intraday (lower wick {r['lower_wick%']:.1f}%")
            print(f"      of price) but buyers stepped in — closed near top of day's range.")
            print(f"      This is the SAME pattern to look for in individual stocks.")
        if r["bb_reversal"]:
            print(f"  *** BB LOWER BAND: Index dipped to/below lower Bollinger band and recovered.")
        if r["near_support"]:
            print(f"  *** SUPPORT BOUNCE: Index is near 120-day low support level.")

    except Exception as e:
        print(f"{t}: error — {e}")

# ── Step 2: Same pattern in individual stocks ─────────────────────────────────
print("\n\n" + "=" * 60)
print("STEP 2 — Same reversal pattern in Nifty stocks today")
print("=" * 60)
print(f"Downloading 60d history for {len(STOCK_TICKERS)} stocks...\n")

raw = yf.download(
    tickers=STOCK_TICKERS,
    period="60d", interval="1d",
    group_by="ticker", auto_adjust=True,
    threads=True, progress=False,
)

results = []
for ticker in STOCK_TICKERS:
    try:
        df_t = raw[ticker].dropna(how="all")
        r = analyze_reversal(df_t, ticker)
        if r and r["score"] >= 1:
            results.append(r)
    except Exception:
        continue

if not results:
    print("No data — check internet connection.")
else:
    df_res = (
        pd.DataFrame(results)
        .sort_values(["score", "day_chg%"], ascending=[False, False])
        .reset_index(drop=True)
    )

    # ── Full table ──
    display_cols = ["ticker","close","day_chg%","rsi14","score","hammer","bb_reversal","near_support","rsi_bounce","lower_wick%"]
    print(df_res[display_cols].to_string(index=False))

    # ── Strong reversals (score >= 3) ──
    strong = df_res[df_res["score"] >= 3]
    print(f"\n{'='*60}")
    print(f"STRONG REVERSALS — same pattern as BSE today (3-4/4 conditions): {len(strong)}")
    if strong.empty:
        print("  None today — check 2-score stocks above as next-best.")
    else:
        print(strong[display_cols].to_string(index=False))
        print("\nThese stocks showed the SAME bullish reversal structure as BSE today:")
        print("  • Hammer candle (sold off, recovered) OR")
        print("  • Bollinger lower band touch + close above it OR")
        print("  • Near key support bounce")
        print("  • RSI oversold turning up")

    # ── Hammer-only subset ──
    hammers = df_res[df_res["hammer"] == True].sort_values("lower_wick%", ascending=False)
    print(f"\n{'='*60}")
    print(f"HAMMER / PIN-BAR candles today (same candle as BSE showed): {len(hammers)}")
    if hammers.empty:
        print("  None today")
    else:
        print(hammers[["ticker","close","day_chg%","rsi14","lower_wick%","body%","score"]].to_string(index=False))

    # ── BB reversals ──
    bb_rev = df_res[df_res["bb_reversal"] == True].sort_values("day_chg%", ascending=False)
    print(f"\n{'='*60}")
    print(f"BOLLINGER LOWER BAND REVERSALS today: {len(bb_rev)}")
    if bb_rev.empty:
        print("  None today")
    else:
        print(bb_rev[["ticker","close","day_chg%","rsi14","bb_lower","score"]].to_string(index=False))

print("\nDone.")
