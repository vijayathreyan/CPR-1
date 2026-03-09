"""
strategy/v1/v1_1.py  —  Version 1.1
────────────────────────────────────
Base version. Tightest CPR width filter.
All other V1 rules inherited unchanged from strategy/v1/base.py
"""

import copy
from strategy.base_strategy import BaseStrategy
from strategy.v1.base import BASE_PARAMS, RULEBOOK_DATE, DESCRIPTION


class Strategy(BaseStrategy):

    def get_params(self) -> dict:
        p = copy.deepcopy(BASE_PARAMS)
        p["cpr"]["vn_threshold"] = 0.15   # Width% < 0.15% → VN-CPR
        p["cpr"]["n_threshold"]  = 0.25   # Width% < 0.25% → qualifies
        return p

    def get_metadata(self) -> dict:
        return {
            "version":        "1.1",
            "major":          "1",
            "minor":          "1",
            "name":           "V1.1 — Base (Tightest Filter)",
            "rulebook_date":  RULEBOOK_DATE,
            "description":    DESCRIPTION,
            "cpr_band":       "0 – 0.25%",
            "intent":         "Base version — tightest filter",
            "vn_threshold":   0.15,
            "n_threshold":    0.25,
            "changes_from_previous": [
                "Initial version — no prior version to compare against.",
            ],
        }
