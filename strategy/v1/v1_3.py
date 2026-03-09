"""
strategy/v1/v1_3.py  —  Version 1.3
────────────────────────────────────
Tighter than base. Only the highest quality CPR setup days qualify.
All other V1 rules unchanged.
"""

import copy
from strategy.base_strategy import BaseStrategy
from strategy.v1.base import BASE_PARAMS, RULEBOOK_DATE, DESCRIPTION


class Strategy(BaseStrategy):

    def get_params(self) -> dict:
        p = copy.deepcopy(BASE_PARAMS)
        p["cpr"]["vn_threshold"] = 0.13
        p["cpr"]["n_threshold"]  = 0.23
        return p

    def get_metadata(self) -> dict:
        return {
            "version":        "1.3",
            "major":          "1",
            "minor":          "3",
            "name":           "V1.3 — Tighter (Highest Quality)",
            "rulebook_date":  RULEBOOK_DATE,
            "description":    DESCRIPTION,
            "cpr_band":       "0 – 0.23%",
            "intent":         "Tighter than base — highest quality days only",
            "vn_threshold":   0.13,
            "n_threshold":    0.23,
            "changes_from_previous": [
                "VN-CPR threshold tightened: < 0.15%  →  < 0.13%",
                "N-CPR threshold tightened:  < 0.25%  →  < 0.23%",
                "All other V1 parameters unchanged",
            ],
        }
