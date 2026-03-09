"""
core/journal.py
───────────────
Persistence layer. Saves and loads backtest results per strategy version.
Builds a comparison.json that the dashboard uses to show all versions together.

Folder layout created automatically:
  data/results/
  ├── 1.1/
  │   ├── journal.csv       ← full trade-by-trade log
  │   ├── journal.xlsx      ← same + Summary sheet
  │   └── metadata.json     ← run info, params, summary stats
  ├── 1.2/
  │   └── ...
  └── comparison.json       ← aggregated summary across ALL versions
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

DATA_DIR         = Path(__file__).parent.parent / "data" / "results"
COMPARISON_FILE  = DATA_DIR / "comparison.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Save
# ─────────────────────────────────────────────────────────────────────────────

def save_journal(df: pd.DataFrame, version: str,
                 params: dict, source: str = "auto") -> Path:
    """
    Save journal CSV, XLSX, and metadata for a strategy version.
    Also updates data/results/comparison.json.
    Returns the directory path where files were saved.
    """
    version_dir = DATA_DIR / version
    version_dir.mkdir(parents=True, exist_ok=True)

    # CSV
    csv_path = version_dir / "journal.csv"
    df.to_csv(csv_path, index=False)
    log.info(f"📄  journal.csv  → {csv_path}")

    # XLSX with Summary sheet
    xlsx_path = version_dir / "journal.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Journal", index=False)
        _write_summary_sheet(df, writer)
    log.info(f"📊  journal.xlsx → {xlsx_path}")

    # Metadata + summary stats
    summary  = _compute_summary(df)
    metadata = {
        "version":        version,
        "run_date":       datetime.now().isoformat(),
        "data_source":    source,
        "backtest_start": str(df["date"].min()) if "date" in df.columns else "",
        "backtest_end":   str(df["date"].max()) if "date" in df.columns else "",
        "total_rows":     len(df),
        "params":         params,
        "summary":        summary,
    }
    meta_path = version_dir / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, default=str))
    log.info(f"📋  metadata.json → {meta_path}")

    # Update aggregated comparison file
    _update_comparison(version, metadata)

    return version_dir


# ─────────────────────────────────────────────────────────────────────────────
#  Load
# ─────────────────────────────────────────────────────────────────────────────

def load_journal(version: str) -> pd.DataFrame:
    """Load journal CSV for a version. Returns empty DataFrame if not found."""
    path = DATA_DIR / version / "journal.csv"
    if not path.exists():
        log.warning(f"No journal found for version {version} at {path}")
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    return df


def load_metadata(version: str) -> dict:
    """Load metadata JSON for a version. Returns empty dict if not found."""
    path = DATA_DIR / version / "metadata.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def list_versions() -> list:
    """Return list of all versions that have saved journal files, sorted."""
    return sorted(
        [d.name for d in DATA_DIR.iterdir()
         if d.is_dir() and (d / "journal.csv").exists()],
        key=lambda v: tuple(int(x) for x in v.split(".") if x.isdigit())
    )


def load_comparison() -> dict:
    """Load the aggregated comparison data for all saved versions."""
    if not COMPARISON_FILE.exists():
        return {}
    return json.loads(COMPARISON_FILE.read_text())


# ─────────────────────────────────────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _compute_summary(df: pd.DataFrame) -> dict:
    trades = df[df.get("entry_type", pd.Series(dtype=str))
                  .isin(["ORIGINAL","RE-ENTRY"])].copy() \
             if "entry_type" in df.columns else pd.DataFrame()

    if trades.empty:
        return {}

    pnl  = pd.to_numeric(trades["total_pnl_pts"], errors="coerce").dropna()
    wins = trades[trades["trade_outcome"].str.startswith("WIN", na=False)]
    loss = trades[trades["trade_outcome"] == "LOSS"]
    full = trades[trades["trade_outcome"] == "WIN-FULL"]

    n        = len(trades)
    win_rate = len(wins)/n*100 if n else 0
    avg_win  = float(pnl[pnl>0].mean()) if (pnl>0).any() else 0.0
    avg_loss = float(pnl[pnl<0].mean()) if (pnl<0).any() else 0.0
    exp      = (win_rate/100*avg_win) + ((1-win_rate/100)*avg_loss)
    gp       = float(pnl[pnl>0].sum())
    gl       = float(abs(pnl[pnl<0].sum()))
    pf       = round(gp/gl, 2) if gl > 0 else None
    cum      = pnl.cumsum()
    max_dd   = float((cum.cummax()-cum).max())

    return {
        "total_trades":  n,
        "win_rate":      round(win_rate, 2),
        "win_full_rate": round(len(full)/n*100, 2) if n else 0,
        "loss_rate":     round(len(loss)/n*100, 2) if n else 0,
        "total_pnl":     round(float(pnl.sum()), 2),
        "avg_win":       round(avg_win, 2),
        "avg_loss":      round(avg_loss, 2),
        "expectancy":    round(exp, 2),
        "profit_factor": pf,
        "max_drawdown":  round(max_dd, 2),
        "gross_profit":  round(gp, 2),
        "gross_loss":    round(gl, 2),
    }


def _update_comparison(version: str, metadata: dict):
    data = {}
    if COMPARISON_FILE.exists():
        try:
            data = json.loads(COMPARISON_FILE.read_text())
        except Exception:
            data = {}
    data[version] = {
        "run_date":       metadata["run_date"],
        "params":         metadata["params"],
        "summary":        metadata["summary"],
        "backtest_start": metadata.get("backtest_start",""),
        "backtest_end":   metadata.get("backtest_end",""),
    }
    COMPARISON_FILE.write_text(json.dumps(data, indent=2, default=str))
    log.info(f"🔄  comparison.json updated with version {version}")


def _write_summary_sheet(df: pd.DataFrame, writer):
    summary = _compute_summary(df)
    if not summary:
        return
    rows = [{"Metric": k.replace("_"," ").title(), "Value": v}
            for k, v in summary.items()]
    pd.DataFrame(rows).to_excel(writer, sheet_name="Summary", index=False)
