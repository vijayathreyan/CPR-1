"""
strategy/v1/v1_2.py  —  Version 1.2
────────────────────────────────────
Marginally wider CPR filter. Captures slightly more setup days.
All other V1 rules unchanged.
"""

import copy
from strategy.base_strategy import BaseStrategy
from strategy.v1.base import BASE_PARAMS, RULEBOOK_DATE, DESCRIPTION


class Strategy(BaseStrategy):

    def get_params(self) -> dict:
        p = copy.deepcopy(BASE_PARAMS)
        p["cpr"]["vn_threshold"] = 0.17
        p["cpr"]["n_threshold"]  = 0.27
        return p

    def get_metadata(self) -> dict:
        return {
            "version":        "1.2",
            "major":          "1",
            "minor":          "2",
            "name":           "V1.2 — Marginally Wider",
            "rulebook_date":  RULEBOOK_DATE,
            "description":    DESCRIPTION,
            "cpr_band":       "0 – 0.27%",
            "intent":         "Marginally wider — captures slightly more days",
            "vn_threshold":   0.17,
            "n_threshold":    0.27,
            "changes_from_previous": [
                "VN-CPR threshold widened:  < 0.15%  →  < 0.17%",
                "N-CPR threshold widened:   < 0.25%  →  < 0.27%",
                "All other V1 parameters unchanged",
            ],
        }
