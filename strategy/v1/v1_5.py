"""
strategy/v1/v1_5.py  —  Version 1.5
────────────────────────────────────
Most restrictive. Very few, very high-quality setup days only.
All other V1 rules unchanged.
"""

import copy
from strategy.base_strategy import BaseStrategy
from strategy.v1.base import BASE_PARAMS, RULEBOOK_DATE, DESCRIPTION


class Strategy(BaseStrategy):

    def get_params(self) -> dict:
        p = copy.deepcopy(BASE_PARAMS)
        p["cpr"]["vn_threshold"] = 0.12
        p["cpr"]["n_threshold"]  = 0.20
        return p

    def get_metadata(self) -> dict:
        return {
            "version":        "1.5",
            "major":          "1",
            "minor":          "5",
            "name":           "V1.5 — Most Restrictive",
            "rulebook_date":  RULEBOOK_DATE,
            "description":    DESCRIPTION,
            "cpr_band":       "0 – 0.20%",
            "intent":         "Most restrictive — very few, very high-quality days",
            "vn_threshold":   0.12,
            "n_threshold":    0.20,
            "changes_from_previous": [
                "VN-CPR threshold tightened: < 0.15%  →  < 0.12%",
                "N-CPR threshold tightened:  < 0.25%  →  < 0.20%",
                "All other V1 parameters unchanged",
            ],
        }
