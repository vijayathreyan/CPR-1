"""
core/data_fetcher.py
────────────────────
Unified data layer. Kite Connect (primary) + yfinance (fallback).
Engine and strategy code never import kiteconnect or yfinance directly —
they always call this module.

Sources:
  'kite'     — Zerodha Kite Connect (requires valid session)
  'yfinance' — Yahoo Finance (daily: full history | 3-min: last 60 days only)
  'auto'     — tries Kite first, silently falls back to yfinance on failure
"""

import time
import logging
import pandas as pd
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

NIFTY_TOKEN = 256265   # NSE:NIFTY 50 instrument token on Kite Connect

# Global cache for Kite client — initialized once per run
_kite_client_cache = None


# ─────────────────────────────────────────────────────────────────────────────
#  Kite helpers
# ─────────────────────────────────────────────────────────────────────────────

def _kite():
    """
    Attempts to get Kite client with timeout.
    Caches the authenticated client globally to avoid re-authentication per call.
    Returns None if Kite is unavailable for any reason.
    """
    global _kite_client_cache
    
    # Return cached client if already initialized
    if _kite_client_cache is not None:
        return _kite_client_cache
    
    from concurrent.futures import ThreadPoolExecutor, TimeoutError
    from core.kite_auth import get_kite_client
    
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(get_kite_client)
            _kite_client_cache = future.result(timeout=120)  # 120-second timeout
            return _kite_client_cache
    except TimeoutError:
        log.warning("⏱  Kite authentication timeout (>120s) — falling back to yfinance")
        return None
    except Exception as e:
        log.warning(f"⚠  Kite unavailable: {type(e).__name__}: {e}")
        return None


def _kite_daily(start: str, end: str) -> pd.DataFrame:
    kite = _kite()
    if not kite:
        raise ConnectionError("Kite not available")

    frames = []
    s   = datetime.strptime(start, "%Y-%m-%d")
    e   = datetime.strptime(end,   "%Y-%m-%d")
    cur = s

    while cur < e:
        chunk = min(cur + timedelta(days=365), e)
        try:
            recs = kite.historical_data(
                NIFTY_TOKEN,
                cur.strftime("%Y-%m-%d"),
                chunk.strftime("%Y-%m-%d"),
                "day",
            )
            if recs:
                df = pd.DataFrame(recs)
                df["date"] = pd.to_datetime(df["date"]).dt.date
                frames.append(df[["date","open","high","low","close","volume"]])
        except Exception as ex:
            log.warning(f"  Kite daily chunk {cur.date()}: {ex}")
        time.sleep(0.35)
        cur = chunk + timedelta(days=1)

    if not frames:
        raise ValueError("No daily data returned from Kite")
    return (pd.concat(frames)
              .drop_duplicates("date")
              .sort_values("date")
              .reset_index(drop=True))


def _kite_intraday(trade_date: str) -> pd.DataFrame:
    kite = _kite()
    if not kite:
        raise ConnectionError("Kite not available")
    try:
        recs = kite.historical_data(
            NIFTY_TOKEN, trade_date, trade_date, "3minute"
        )
    except Exception as e:
        log.warning(f"  Kite intraday {trade_date}: {e}")
        return pd.DataFrame()

    if not recs:
        return pd.DataFrame()
    df = pd.DataFrame(recs)
    df["datetime"] = pd.to_datetime(df["date"])
    return (df[["datetime","open","high","low","close","volume"]]
              .sort_values("datetime")
              .reset_index(drop=True))


# ─────────────────────────────────────────────────────────────────────────────
#  yfinance helpers
# ─────────────────────────────────────────────────────────────────────────────

def _yf_daily(start: str, end: str) -> pd.DataFrame:
    import yfinance as yf
    raw = yf.Ticker("^NSEI").history(
        start=start, end=end, interval="1d", auto_adjust=True
    )
    if raw.empty:
        raise ValueError("yfinance returned empty daily data for ^NSEI")
    raw = raw.reset_index()
    raw.columns = [c.lower() for c in raw.columns]
    raw["date"] = pd.to_datetime(raw["date"]).dt.date
    return (raw[["date","open","high","low","close","volume"]]
              .dropna(subset=["close"])
              .sort_values("date")
              .reset_index(drop=True))


def _yf_intraday(trade_date: str) -> pd.DataFrame:
    import yfinance as yf
    s = datetime.strptime(trade_date, "%Y-%m-%d")
    e = s + timedelta(days=1)
    raw = yf.Ticker("^NSEI").history(
        start=s.strftime("%Y-%m-%d"),
        end=e.strftime("%Y-%m-%d"),
        interval="5m",
        auto_adjust=True,
    )
    if raw.empty:
        return pd.DataFrame()
    raw = raw.reset_index()
    raw.columns = [c.lower() for c in raw.columns]
    if "datetime" not in raw.columns and "date" in raw.columns:
        raw = raw.rename(columns={"date": "datetime"})
    raw["datetime"] = pd.to_datetime(raw["datetime"])
    return (raw[["datetime","open","high","low","close","volume"]]
              .sort_values("datetime")
              .reset_index(drop=True))


# ─────────────────────────────────────────────────────────────────────────────
#  Public API — called by engine/backtest_runner.py only
# ─────────────────────────────────────────────────────────────────────────────

def get_daily_data(start: str, end: str, source: str = "auto") -> pd.DataFrame:
    """
    Fetch daily OHLCV data for Nifty 50.
    source: 'kite' | 'yfinance' | 'auto'
    """
    if source == "kite":
        return _kite_daily(start, end)
    if source == "yfinance":
        return _yf_daily(start, end)
    try:
        return _kite_daily(start, end)
    except Exception as e:
        log.warning(f"Kite daily failed ({e}), using yfinance")
        return _yf_daily(start, end)


def get_intraday_data(trade_date: str, source: str = "auto") -> pd.DataFrame:
    """
    Fetch 3-minute intraday OHLCV for a single trading date.
    source: 'kite' | 'yfinance' | 'auto'
    Note: yfinance only supports last ~60 days for 3-min data.
    """
    if source == "kite":
        return _kite_intraday(trade_date)
    if source == "yfinance":
        return _yf_intraday(trade_date)
    try:
        df = _kite_intraday(trade_date)
        if df.empty:
            raise ValueError("Empty Kite response")
        return df
    except Exception as e:
        log.warning(f"Kite intraday failed ({e}), using yfinance")
        return _yf_intraday(trade_date)
