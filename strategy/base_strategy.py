"""
strategy/base_strategy.py
─────────────────────────
Abstract base class that EVERY strategy version must implement.

The engine calls only two methods:
  strategy.get_params()   → dict of all thresholds and rules
  strategy.get_metadata() → human-readable info for the dashboard

This contract never changes. Adding a new version = creating a new file
that subclasses this and fills in these two methods.
"""

from abc import ABC, abstractmethod


class BaseStrategy(ABC):

    @abstractmethod
    def get_params(self) -> dict:
        """
        Return all strategy parameters as a nested dict.

        Required structure (engine raises KeyError if missing):
          cpr:
            vn_threshold      float   CPR Width% below which = VN-CPR
            n_threshold       float   CPR Width% below which = N-CPR
          sl:
            max_sl_pts        int     fixed SL cap in index points
            lookback          int     structural SL: N prior candles
          targets:
            tp1_r_multiple    float   TP-1 = Entry + R × this value
          tsl:
            buffer_pts        float   TSL = fast-EMA − this
            update_mins       int     recalculate TSL every N minutes
          ema:
            fast              int     fast EMA period on 3-min candles
            slow              int     slow EMA period on 3-min candles
          session:
            entry_start       str     "HH:MM" earliest entry time
            entry_cutoff      str     "HH:MM" no new entries after this
            hard_exit         str     "HH:MM" all positions closed by
            obs_times         list    ["HH:MM", ...] candle close times
            min_obs_above     int     min candles above TC required
          lot_size            int     contracts per lot
        """
        ...

    @abstractmethod
    def get_metadata(self) -> dict:
        """
        Return human-readable version information for the dashboard.

        Required keys:
          version               str   "1.1"
          major                 str   "1"
          minor                 str   "1"
          name                  str   "V1.1 — Base (Tightest Filter)"
          rulebook_date         str   "February 2026"
          description           str   paragraph describing the strategy
          cpr_band              str   "0 – 0.25%"
          intent                str   one-line intent of this variation
          vn_threshold          float
          n_threshold           float
          changes_from_previous list  bullet points of what changed
        """
        ...

    def validate(self):
        """Check all required param keys are present. Called before backtest."""
        p = self.get_params()
        required = [
            ("cpr",     "vn_threshold"),
            ("cpr",     "n_threshold"),
            ("sl",      "max_sl_pts"),
            ("sl",      "lookback"),
            ("targets", "tp1_r_multiple"),
            ("tsl",     "buffer_pts"),
            ("tsl",     "update_mins"),
            ("ema",     "fast"),
            ("ema",     "slow"),
            ("session", "entry_start"),
            ("session", "entry_cutoff"),
            ("session", "hard_exit"),
        ]
        for group, key in required:
            assert group in p and key in p[group], \
                f"Strategy params missing: {group}.{key}"
        return True
