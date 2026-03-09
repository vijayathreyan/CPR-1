"""
strategy/__init__.py
────────────────────
Public API for the strategy layer.
All callers import from here — never from submodules directly.
"""

from strategy.registry import (
    load,
    all_versions,
    major_versions,
    minor_versions_of,
    load_major_base,
)

# Aliases for readability
load_strategy      = load
available_versions = all_versions
