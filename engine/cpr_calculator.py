"""
engine/cpr_calculator.py
────────────────────────
Pure CPR mathematics. No data fetching, no side effects, no hardcoded values.
Every threshold and rule comes from the strategy params dict.
"""

import pandas as pd
import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
#  CPR Level Calculations
# ─────────────────────────────────────────────────────────────────────────────

def calculate_cpr(prev_high: float, prev_low: float, prev_close: float) -> dict:
    """Calculate Pivot, BC, TC, width from previous session OHLC."""
    pp = (prev_high + prev_low + prev_close) / 3
    bc = (pp + prev_low)  / 2
    tc = (pp + prev_high) / 2
    return {
        "pp":        round(pp, 2),
        "bc":        round(bc, 2),
        "tc":        round(tc, 2),
        "width_pts": round(tc - bc, 2),
        "width_pct": round((tc - bc) / prev_close * 100, 4),
    }


def classify_cpr(width_pct: float, params: dict) -> str:
    """
    Classify CPR type using strategy thresholds.
    Returns: 'VN-CPR' | 'N-CPR' | 'S-CPR' | 'W-CPR'
    """
    vn = params["cpr"]["vn_threshold"]
    n  = params["cpr"]["n_threshold"]
    if width_pct < vn:
        return "VN-CPR"
    elif width_pct < n:
        return "N-CPR"
    elif width_pct < 0.50:
        return "S-CPR"
    return "W-CPR"


def is_valid_cpr(cpr_type: str) -> bool:
    """Only VN-CPR and N-CPR are qualifying setup days."""
    return cpr_type in ("VN-CPR", "N-CPR")


# ─────────────────────────────────────────────────────────────────────────────
#  AB-CPR Check (Ascending / Bullish CPR)
# ─────────────────────────────────────────────────────────────────────────────

def check_ab_cpr(today_bc: float, yesterday_tc: float) -> tuple:
    """
    AB-CPR: Yesterday's TC < Today's BC (CPR has moved up = bullish bias).
    Returns (is_ab_cpr: bool, spread_pts: float)
    """
    spread = round(today_bc - yesterday_tc, 2)
    return spread > 0, spread


# ─────────────────────────────────────────────────────────────────────────────
#  Opening Window Observation (PO > TC)
# ─────────────────────────────────────────────────────────────────────────────

def check_price_above_tc(df_3min: pd.DataFrame,
                          tc: float, params: dict) -> tuple:
    """
    Check how many observation candle closes are above TC.
    Returns (po_above_tc: bool, count: int, closes: list)
    """
    obs_times    = params["session"]["obs_times"]
    min_required = params["session"]["min_obs_above"]

    closes = []
    for t in obs_times:
        h, m = map(int, t.split(":"))
        row  = df_3min[
            (df_3min["datetime"].dt.hour   == h) &
            (df_3min["datetime"].dt.minute == m)
        ]
        closes.append(float(row["close"].iloc[0]) if not row.empty else None)

    valid       = [c for c in closes if c is not None]
    count_above = sum(1 for c in valid if c > tc)
    return count_above >= min_required, count_above, closes


# ─────────────────────────────────────────────────────────────────────────────
#  EMA Calculations
# ─────────────────────────────────────────────────────────────────────────────

def add_emas(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Add fast and slow EMA columns to a 3-min OHLCV DataFrame."""
    fast = params["ema"]["fast"]
    slow = params["ema"]["slow"]
    df   = df.copy()
    df[f"ema{fast}"] = df["close"].ewm(span=fast, adjust=False).mean()
    df[f"ema{slow}"] = df["close"].ewm(span=slow, adjust=False).mean()
    return df


def check_ema_stack(row: pd.Series, params: dict) -> tuple:
    """
    EMA-1: Close > fast-EMA
    EMA-2: fast-EMA > slow-EMA
    Returns (ema1_ok, ema2_ok, ema_fast_val, ema_slow_val)
    """
    fast = params["ema"]["fast"]
    slow = params["ema"]["slow"]
    ef   = row[f"ema{fast}"]
    es   = row[f"ema{slow}"]
    return (
        bool(row["close"] > ef),
        bool(ef > es),
        round(float(ef), 2),
        round(float(es), 2),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Stop Loss
# ─────────────────────────────────────────────────────────────────────────────

def calculate_initial_sl(entry_price: float,
                          prior_candles: pd.DataFrame,
                          params: dict) -> tuple:
    """
    SL = lower of:
      Method A (fixed cap):   Entry − max_sl_pts
      Method B (structural):  Lowest low of prior N candles

    Returns (sl_price, method_label, r_value)
    """
    max_sl = params["sl"]["max_sl_pts"]
    lb     = params["sl"]["lookback"]

    sl_a = entry_price - max_sl

    if len(prior_candles) >= lb:
        sl_b = float(prior_candles["low"].iloc[-lb:].min())
    elif not prior_candles.empty:
        sl_b = float(prior_candles["low"].min())
    else:
        sl_b = sl_a

    if sl_b < sl_a:
        sl_price, method = sl_b, "STRUCTURAL"
    else:
        sl_price, method = sl_a, "FIXED-40"

    r = round(entry_price - sl_price, 2)
    return round(sl_price, 2), method, r


# ─────────────────────────────────────────────────────────────────────────────
#  Trailing Stop Loss
# ─────────────────────────────────────────────────────────────────────────────

def update_tsl(current_tsl: float,
               ema_fast_val: float,
               params: dict) -> float:
    """
    TSL = MAX(current_tsl, fast-EMA − buffer)
    TSL only ever moves up — never down.
    """
    buf = params["tsl"]["buffer_pts"]
    return round(max(current_tsl, ema_fast_val - buf), 2)


# ─────────────────────────────────────────────────────────────────────────────
#  Market Context Tags
# ─────────────────────────────────────────────────────────────────────────────

def classify_vix(vix) -> str:
    if vix is None or (isinstance(vix, float) and pd.isna(vix)):
        return "UNKNOWN"
    return "HI-VIX" if vix > 20 else ("LO-VIX" if vix < 12 else "NORMAL")


def classify_gap(open_price: float, prev_close: float) -> tuple:
    """Returns (gap_type, gap_pts)"""
    gap_pts = open_price - prev_close
    gap_pct = gap_pts / prev_close * 100
    if   gap_pct >  0.3: return "GAP-UP",   round(gap_pts, 2)
    elif gap_pct < -0.3: return "GAP-DOWN", round(gap_pts, 2)
    return "FLAT", round(gap_pts, 2)


def classify_special_day(date) -> str:
    """Tag Nifty expiry days (weekly Thursday / monthly last Thursday)."""
    d = pd.Timestamp(date)
    if d.weekday() == 3:  # Thursday
        nxt = d + pd.Timedelta(days=7)
        return "EXP-M" if nxt.month != d.month else "EXP-W"
    return "NONE"
