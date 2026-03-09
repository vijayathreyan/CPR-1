"""
engine/backtest_runner.py
──────────────────────────
Orchestrates the full backtest loop across all trading days.
Reads parameters exclusively from the strategy object.
Calls data_fetcher for prices, calls trade_simulator per day.
Never hardcodes any threshold or rule.
"""

import logging
import warnings
warnings.filterwarnings("ignore")

import pandas as pd

from engine.cpr_calculator import (
    calculate_cpr, classify_cpr, is_valid_cpr,
    check_ab_cpr, check_price_above_tc, add_emas,
    classify_vix, classify_gap, classify_special_day,
)
from engine.trade_simulator import simulate_trade

log = logging.getLogger(__name__)


def run(strategy,
        daily_df: pd.DataFrame,
        get_intraday_fn,
        source: str = "auto") -> pd.DataFrame:
    """
    Run a full backtest.

    Args:
        strategy        : loaded strategy instance (has .get_params())
        daily_df        : full daily OHLCV DataFrame
        get_intraday_fn : callable(trade_date: str) → 3-min DataFrame
        source          : label for logging only

    Returns:
        journal DataFrame (every calendar day, including non-setup days)
    """
    params  = strategy.get_params()
    daily   = daily_df.sort_values("date").reset_index(drop=True)
    records = []
    skipped = 0
    n       = len(daily)

    log.info(f"  Processing {n} daily bars…")

    for i in range(1, n):
        today = daily.iloc[i]
        prev  = daily.iloc[i - 1]
        prev2 = daily.iloc[i - 2] if i >= 2 else None

        trade_date = str(today["date"])
        prev_close = float(prev["close"])
        open_price = float(today["open"])

        # ── Group A — market context ─────────────────────────────────────────
        gap_type, gap_pts = classify_gap(open_price, prev_close)
        special_tag       = classify_special_day(today["date"])
        dow               = pd.Timestamp(today["date"]).strftime("%a")

        # ── Group B — CPR levels ─────────────────────────────────────────────
        cpr      = calculate_cpr(float(prev["high"]), float(prev["low"]), prev_close)
        cpr_type = classify_cpr(cpr["width_pct"], params)
        valid_cpr = is_valid_cpr(cpr_type)

        yesterday_tc = None
        if prev2 is not None:
            c2 = calculate_cpr(
                float(prev2["high"]), float(prev2["low"]), float(prev2["close"])
            )
            yesterday_tc = c2["tc"]

        ab_cpr, ab_spread = False, 0.0
        if yesterday_tc is not None:
            ab_cpr, ab_spread = check_ab_cpr(cpr["bc"], yesterday_tc)

        base = _base_record(
            trade_date, dow, prev_close, special_tag, gap_type, gap_pts,
            float(prev["high"]), float(prev["low"]),
            cpr, cpr_type, yesterday_tc, ab_cpr, ab_spread,
        )

        # Gate 1: CPR must be valid AND AB-CPR must hold
        if not (valid_cpr and ab_cpr):
            base["setup_valid"] = "NO"
            records.append(base)
            continue

        # ── Fetch intraday data ──────────────────────────────────────────────
        try:
            intraday = get_intraday_fn(trade_date)
        except Exception as ex:
            log.warning(f"  ⚠  {trade_date}: intraday fetch error — {ex}")
            skipped += 1
            continue

        if intraday is None or intraday.empty:
            skipped += 1
            continue

        intraday = add_emas(intraday, params)

        # ── Group C — opening window observation ─────────────────────────────
        po_ok, count_above, obs_closes = check_price_above_tc(
            intraday, cpr["tc"], params
        )
        base.update({
            "obs_9_21":         obs_closes[0],
            "obs_9_24":         obs_closes[1],
            "obs_9_27":         obs_closes[2],
            "obs_9_30":         obs_closes[3],
            "candles_above_tc": count_above,
            "po_above_tc":      "YES" if po_ok else "NO",
        })

        # Gate 2: PO > TC
        setup_valid = valid_cpr and ab_cpr and po_ok
        base["setup_valid"] = "YES" if setup_valid else "NO"

        if not setup_valid:
            records.append(base)
            continue

        # ── Simulate trade ───────────────────────────────────────────────────
        trade = simulate_trade(intraday, params)
        base.update(trade)
        records.append(base)

        pnl     = trade.get("total_pnl_pts") or 0
        outcome = trade.get("trade_outcome", "NO TRADE")
        log.info(f"  {trade_date}  {cpr_type:<8}  {outcome:<13}  {pnl:+.1f} pts")

    log.info(f"\n  Done — {len(records)} rows, {skipped} skipped.")
    return pd.DataFrame(records)


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: blank base record for one day
# ─────────────────────────────────────────────────────────────────────────────

def _base_record(date, dow, prev_close, special, gap_type, gap_pts,
                 prev_high, prev_low, cpr, cpr_type,
                 yesterday_tc, ab_cpr, ab_spread) -> dict:
    return {
        # Group A
        "date": date, "day_of_week": dow, "prev_close": prev_close,
        "india_vix": None, "vix_tag": "UNKNOWN",
        "special_day": special, "market_bias": gap_type, "gap_pts": gap_pts,
        # Group B
        "prev_high": prev_high, "prev_low": prev_low,
        "pp": cpr["pp"], "bc": cpr["bc"], "tc": cpr["tc"],
        "cpr_width_pts": cpr["width_pts"], "cpr_width_pct": cpr["width_pct"],
        "cpr_type": cpr_type,
        "yesterday_tc": yesterday_tc,
        "ab_cpr": "YES" if ab_cpr else "NO",
        "ab_cpr_spread": ab_spread,
        # Group C (defaults — overwritten after intraday fetch)
        "obs_9_21": None, "obs_9_24": None, "obs_9_27": None, "obs_9_30": None,
        "candles_above_tc": None, "po_above_tc": None,
        "setup_valid": "NO",
        # Groups D–G (defaults — overwritten by simulate_trade)
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
        **{f"tsl_chk_{n}": None for n in range(1, 9)},
        "qty2_exit_type": None, "qty2_exit_price": None,
        "qty2_exit_time": None, "qty2_pnl_pts": None,
        "mae_pts": None, "total_pnl_pts": None,
        "trade_duration": None, "trade_outcome": "NO TRADE",
    }
