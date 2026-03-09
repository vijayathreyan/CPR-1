"""
strategy/registry.py
────────────────────
Auto-discovers every strategy version by scanning the strategy/ folder.
You NEVER need to edit this file when adding new versions.

File naming convention (strictly followed):
  strategy/v{MAJOR}/v{MAJOR}_{MINOR}.py

Examples that auto-register:
  strategy/v1/v1_1.py   →  version "1.1"
  strategy/v1/v1_2.py   →  version "1.2"
  strategy/v2/v2_1.py   →  version "2.1"
  strategy/v3/v3_4.py   →  version "3.4"

To add Version 2.1:
  1. Create folder:  strategy/v2/
  2. Create file:    strategy/v2/__init__.py   (empty)
  3. Create file:    strategy/v2/base.py       (V2 shared rules)
  4. Create file:    strategy/v2/v2_1.py       (minor variation)
  5. Done — registry finds it automatically on next run.
"""

import re
import importlib
import logging
from pathlib import Path

log             = logging.getLogger(__name__)
_STRATEGY_DIR   = Path(__file__).parent
_VERSION_REGEX  = re.compile(r"^v(\d+)[/\\]v(\d+)_(\d+)\.py$")


def _scan() -> dict:
    """
    Scan strategy/ and return {version_id: module_path} dict.
    e.g. {"1.1": "strategy.v1.v1_1", "1.2": "strategy.v1.v1_2"}
    """
    found = {}
    for path in sorted(_STRATEGY_DIR.rglob("v*_*.py")):
        rel = path.relative_to(_STRATEGY_DIR)
        m   = _VERSION_REGEX.match(str(rel))
        if not m:
            continue
        folder_major = m.group(1)
        file_major   = m.group(2)
        minor        = m.group(3)
        if folder_major != file_major:
            continue  # skip mismatched e.g. v1/v2_1.py
        vid  = f"{folder_major}.{minor}"
        mpath = f"strategy.v{folder_major}.v{file_major}_{minor}"
        found[vid] = mpath
    return found


def all_versions() -> list:
    """Sorted list of all discovered version IDs e.g. ['1.1','1.2','2.1']"""
    return sorted(
        _scan().keys(),
        key=lambda v: tuple(int(x) for x in v.split("."))
    )


def major_versions() -> list:
    """Unique major version numbers e.g. ['1', '2']"""
    seen = []
    for v in all_versions():
        maj = v.split(".")[0]
        if maj not in seen:
            seen.append(maj)
    return seen


def minor_versions_of(major: str) -> list:
    """All minor version IDs for one major e.g. ['1.1','1.2','1.3']"""
    return [v for v in all_versions() if v.startswith(f"{major}.")]


def load(version_id: str):
    """
    Load and return a Strategy instance for the given version_id.
    Raises ValueError if the version is not found.
    """
    registry = _scan()
    if version_id not in registry:
        raise ValueError(
            f"Strategy '{version_id}' not found.\n"
            f"Available: {list(registry.keys())}\n"
            f"Check that strategy/v{version_id.split('.')[0]}/"
            f"v{'_'.join(version_id.split('.'))}.py exists."
        )
    module   = importlib.import_module(registry[version_id])
    strategy = module.Strategy()
    log.info(f"📦  Loaded: {strategy.get_metadata()['name']}")
    return strategy


def load_major_base(major: str):
    """
    Load the base module for a major version (for dashboard descriptions).
    Returns None if no base.py exists for that major.
    """
    try:
        return importlib.import_module(f"strategy.v{major}.base")
    except ModuleNotFoundError:
        return None
