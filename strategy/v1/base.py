"""
strategy/v1/base.py
────────────────────
Major Version 1 — ALL shared rules for every V1.x minor version.

Minor versions (v1_1.py … v1_5.py) inherit BASE_PARAMS and only
override the CPR width thresholds. Everything else is defined here.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHEN V2 RULEBOOK ARRIVES FROM YOUR MENTOR:
  1. Create  strategy/v2/base.py   ← put ALL V2 rules here
  2. Create  strategy/v2/v2_1.py   ← minor variation 1
  3. Create  strategy/v2/v2_2.py   ← minor variation 2  (etc.)
  4. Run:    python run_backtest.py --major 2 --source kite
  Dashboard shows Major V2 automatically. Nothing else changes.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ── Metadata shown in dashboard ───────────────────────────────────────────────
MAJOR_VERSION   = "1"
RULEBOOK_NAME   = "CPR Long Only — Intraday Bullish Momentum"
RULEBOOK_DATE   = "February 2026 (updated March 2026)"
INSTRUMENT      = "Nifty 50 Index (NSE Spot)"
DIRECTION       = "Long Only (Buy)"
TIMEFRAME_SETUP = "Daily OHLC (previous session)"
TIMEFRAME_EXEC  = "3-Minute Candlestick"

DESCRIPTION = """
Exploit Narrow CPR days where price opens bullishly above TC with momentum
confirmed by EMA alignment on the 3-minute chart.

Core insight: A Narrow CPR (small difference between TC and BC) indicates
low volatility and market indecision on the previous session — a compressed
range. When today's price opens ABOVE TC of this Narrow CPR AND the CPR is
ascending (yesterday's TC < today's BC = AB-CPR condition), the market
signals a bullish continuation bias.

The EMA stack confirmation (Close > 5-EMA > 20-EMA on 3-min chart) validates
that intraday momentum is aligned before entry. The result is a structured,
rule-based entry with defined Stop Loss and a two-lot exit plan (TP-1 partial
exit, then trailing stop on the remainder).

Across V1.x minor versions ONLY the CPR Width threshold changes.
All other parameters — Stop Loss, targets, TSL, session times, EMAs — are
identical across all five minor versions.
"""

MAJOR_CHANGES_FROM_PREVIOUS = [
    "Initial major version. No prior major version exists.",
]

# ── Shared parameters — used by ALL V1.x minor versions ──────────────────────
# Minor versions do deepcopy of this dict and override cpr thresholds only.
BASE_PARAMS = {

    # CPR thresholds — each minor version sets these
    "cpr": {
        "vn_threshold": None,   # Width% < this → VN-CPR
        "n_threshold":  None,   # Width% < this → N-CPR (includes VN band)
    },

    # Stop Loss — Section 6.1
    # Use the LOWER (more protective) of Method A and Method B
    "sl": {
        "max_sl_pts": 40,       # Method A: Entry − 40 pts (fixed cap)
        "lookback":   6,        # Method B: lowest low of prior 6 candles
    },

    # Profit Target — Section 6.2
    "targets": {
        "tp1_r_multiple": 1.2,  # TP-1 (Qty-1 exit) = Entry + R × 1.2
                                 # Qty-2 has no fixed target; exits via TSL or time
    },

    # Trailing Stop Loss — Section 7.1 (activated after TP-1 is hit)
    "tsl": {
        "buffer_pts":  10,      # TSL price = 5-EMA − 10 pts
        "update_mins": 15,      # Recalculate TSL every 15 minutes
                                 # (every 5th 3-minute candle)
    },

    # EMA settings — evaluated on 3-minute candles
    "ema": {
        "fast": 5,              # 5-period EMA
        "slow": 20,             # 20-period EMA
    },

    # Session rules
    "session": {
        "entry_start":   "09:35",          # No entry before this
        "entry_cutoff":  "13:00",          # No new entries after this
        "hard_exit":     "14:40",          # All positions closed by this time
        "obs_times":     ["09:21","09:24","09:27","09:30"],  # Observation window
        "min_obs_above": 2,                # Min closes above TC required (of 4)
    },

    # Position sizing
    "lot_size": 50,                        # 1 lot = 50 units of Nifty
}
