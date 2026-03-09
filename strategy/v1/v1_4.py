"""
strategy/v1/v1_4.py  —  Version 1.4
────────────────────────────────────
Wider filter. More trades, lower quality threshold.
All other V1 rules unchanged.
"""

import copy
from strategy.base_strategy import BaseStrategy
from strategy.v1.base import BASE_PARAMS, RULEBOOK_DATE, DESCRIPTION


class Strategy(BaseStrategy):

    def get_params(self) -> dict:
        p = copy.deepcopy(BASE_PARAMS)
        p["cpr"]["vn_threshold"] = 0.20
        p["cpr"]["n_threshold"]  = 0.30
        return p

    def get_metadata(self) -> dict:
        return {
            "version":        "1.4",
            "major":          "1",
            "minor":          "4",
            "name":           "V1.4 — Wider (More Trades)",
            "rulebook_date":  RULEBOOK_DATE,
            "description":    DESCRIPTION,
            "cpr_band":       "0 – 0.30%",
            "intent":         "Wider — more trades, lower quality filter",
            "vn_threshold":   0.20,
            "n_threshold":    0.30,
            "changes_from_previous": [
                "VN-CPR threshold widened: < 0.15%  →  < 0.20%",
                "N-CPR threshold widened:  < 0.25%  →  < 0.30%",
                "All other V1 parameters unchanged",
            ],
        }
