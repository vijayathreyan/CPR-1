"""
engine/trade_simulator.py
──────────────────────────
Simulates one complete trading day following the CPR rule book.
All parameters come from the strategy object — nothing is hardcoded.
Called once per qualifying day by backtest_runner.py.
"""

import numpy as np
import pandas as pd
import logging

from engine.cpr_calculator import (
    add_emas, check_ema_stack,
    calculate_initial_sl, update_tsl,
)

log = logging.getLogger(__name__)


def _to_min(t_str: str) -> int:
    h, m = map(int, t_str.split(":"))
    return h * 60 + m


def _blank_trade() -> dict:
    return {
        "signal_candle_time": None, "signal_open": None,
        "signal_high": None, "signal_low": None, "signal_close": None,
        "ema_fast_signal": None, "ema_slow_signal": None, "ema_spread": None,
        "entry_condition_met": False, "entry_type": "NO TRADE",
        "entry_price": None, "entry_time": None,
        "sl_method": None, "sl_price": None, "r_value": None, "tp1_price": None,
        "tp1_hit": False, "tp1_exit_price": None,
        "tp1_exit_time": None, "tp1_pnl_pts": None,
        "tsl_activate_price": None, "tsl_activate_time": None,
        "max_price_reached": None, "mfe_pts": None,
        **{f"tsl_chk_{i}": None for i in range(1, 9)},
        "qty2_exit_type": None, "qty2_exit_price": None,
        "qty2_exit_time": None, "qty2_pnl_pts": None,
        "mae_pts": None, "total_pnl_pts": None,
        "trade_duration": None, "trade_outcome": "NO TRADE",
    }


def simulate_trade(df_3min: pd.DataFrame, params: dict) -> dict:
    """
    Simulate one trading day.

    Args:
        df_3min : 3-minute OHLCV DataFrame with 'datetime' column
        params  : strategy.get_params() dict

    Returns:
        dict with all journal columns (Groups D–G)
    """
    if df_3min is None or df_3min.empty:
        return _blank_trade()

    df = add_emas(df_3min, params)

    start_min   = _to_min(params["session"]["entry_start"])
    cutoff_min  = _to_min(params["session"]["entry_cutoff"])
    hard_ex_min = _to_min(params["session"]["hard_exit"])
    tp1_r       = params["targets"]["tp1_r_multiple"]
    tsl_mins    = params["tsl"]["update_mins"]
    fast_k      = params["ema"]["fast"]

    def cm(row):
        return row["datetime"].hour * 60 + row["datetime"].minute

    # ── Find signal candle ───────────────────────────────────────────────────
    entry_idx = None
    for idx, row in df.iterrows():
        c = cm(row)
        if c < start_min or c > cutoff_min:
            continue
        e1, e2, _, _ = check_ema_stack(row, params)
        if e1 and e2:
            entry_idx = idx
            break

    if entry_idx is None:
        return _blank_trade()

    sig  = df.loc[entry_idx]
    e1, e2, ema_f, ema_s = check_ema_stack(sig, params)
    entry_price = float(sig["close"])
    entry_time  = sig["datetime"]

    prior                = df[df.index < entry_idx]
    sl_price, sl_method, r_val = calculate_initial_sl(entry_price, prior, params)
    tp1                  = round(entry_price + r_val * tp1_r, 2)

    result = {
        **_blank_trade(),
        "signal_candle_time": entry_time.strftime("%H:%M"),
        "signal_open":  float(sig["open"]),
        "signal_high":  float(sig["high"]),
        "signal_low":   float(sig["low"]),
        "signal_close": entry_price,
        "ema_fast_signal": ema_f,
        "ema_slow_signal": ema_s,
        "ema_spread":   round(ema_f - ema_s, 2),
        "entry_condition_met": True,
        "entry_type":   "ORIGINAL",
        "entry_price":  entry_price,
        "entry_time":   entry_time.strftime("%H:%M"),
        "sl_method":    sl_method,
        "sl_price":     sl_price,
        "r_value":      r_val,
        "tp1_price":    tp1,
    }

    # ── Trade management loop ────────────────────────────────────────────────
    max_price       =  float("-inf")
    min_price       =  float("inf")
    tp1_hit         = False
    tsl_active      = False
    current_tsl     = None
    last_tsl_upd_m  = None
    tsl_chk_n       = 0
    qty1_exit_price = None
    qty2_exit_price = None
    qty2_exit_type  = None
    qty2_exit_time  = None

    for idx, row in df[df.index > entry_idx].iterrows():
        c     = cm(row)
        close = float(row["close"])
        high  = float(row["high"])
        low   = float(row["low"])
        ema5  = float(row[f"ema{fast_k}"])

        max_price = max(max_price, high)
        min_price = min(min_price, low)

        # Hard time exit
        if c >= hard_ex_min:
            if not tp1_hit:
                qty1_exit_price = close
            qty2_exit_price = close
            qty2_exit_type  = "TIME-EXIT"
            qty2_exit_time  = row["datetime"].strftime("%H:%M")
            break

        # Initial SL hit (before TP-1)
        if not tp1_hit and low <= sl_price:
            qty1_exit_price = sl_price
            qty2_exit_price = sl_price
            qty2_exit_type  = "SL-INITIAL"
            qty2_exit_time  = row["datetime"].strftime("%H:%M")
            break

        # TP-1 hit
        if not tp1_hit and high >= tp1:
            tp1_hit         = True
            qty1_exit_price = tp1
            result["tp1_hit"]            = True
            result["tp1_exit_price"]     = tp1
            result["tp1_exit_time"]      = row["datetime"].strftime("%H:%M")
            result["tp1_pnl_pts"]        = round(tp1 - entry_price, 2)
            result["tsl_activate_price"] = round(ema5, 2)
            result["tsl_activate_time"]  = row["datetime"].strftime("%H:%M")
            current_tsl     = round(ema5, 2)
            tsl_active      = True
            last_tsl_upd_m  = c
            continue

        # TSL management (Qty-2 only, after TP-1)
        if tsl_active:
            if (c - last_tsl_upd_m) >= tsl_mins:
                current_tsl = update_tsl(current_tsl, ema5, params)
                last_tsl_upd_m = c
                tsl_chk_n += 1
                if tsl_chk_n <= 8:
                    result[f"tsl_chk_{tsl_chk_n}"] = current_tsl

            if low <= current_tsl:
                qty2_exit_price = current_tsl
                qty2_exit_type  = "TSL-1"
                qty2_exit_time  = row["datetime"].strftime("%H:%M")
                break

    # Fallback — end of data
    if qty2_exit_price is None:
        last_row        = df.iloc[-1]
        qty2_exit_price = float(last_row["close"])
        qty2_exit_type  = "TIME-EXIT"
        qty2_exit_time  = params["session"]["hard_exit"]
        if not tp1_hit:
            qty1_exit_price = qty2_exit_price

    qty1_pnl  = round((qty1_exit_price or qty2_exit_price) - entry_price, 2)
    qty2_pnl  = round(qty2_exit_price - entry_price, 2)
    total_pnl = round(qty1_pnl + qty2_pnl, 2)
    mfe       = round(max_price - entry_price, 2) if max_price > float("-inf") else 0
    mae       = round(entry_price - min_price, 2) if min_price < float("inf")  else 0

    if qty2_exit_type == "SL-INITIAL":
        outcome = "LOSS"
    elif tp1_hit and qty2_pnl > 0:
        outcome = "WIN-FULL"
    elif tp1_hit and qty2_pnl <= 0:
        outcome = "WIN-PARTIAL"
    elif total_pnl > 0:
        outcome = "WIN-FULL"
    elif total_pnl == 0:
        outcome = "BREAKEVEN"
    else:
        outcome = "LOSS"

    try:
        ex_ts    = pd.Timestamp(
            str(entry_time.date()) + " " + (qty2_exit_time or params["session"]["hard_exit"])
        )
        duration = str(ex_ts - entry_time).split(".")[0][-5:]
    except Exception:
        duration = None

    result.update({
        "max_price_reached": round(max_price, 2) if max_price > float("-inf") else None,
        "mfe_pts":           mfe,
        "qty2_exit_type":    qty2_exit_type,
        "qty2_exit_price":   qty2_exit_price,
        "qty2_exit_time":    qty2_exit_time,
        "qty2_pnl_pts":      qty2_pnl,
        "mae_pts":           mae,
        "total_pnl_pts":     total_pnl,
        "trade_duration":    duration,
        "trade_outcome":     outcome,
    })
    return result
