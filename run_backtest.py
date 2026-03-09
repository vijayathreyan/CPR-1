"""
run_backtest.py
───────────────
Main entry point. Always run from the CPR_Strategy/ root folder.

Usage:
    python run_backtest.py --version 1.1 --source yfinance
    python run_backtest.py --version 1.1 --source kite
    python run_backtest.py --major 1   --source kite        # all of 1.1 → 1.5
    python run_backtest.py --all       --source kite        # every version
    python run_backtest.py --version 1.1 --source kite --start 2020-01-01 --end 2023-12-31
"""

import argparse
import logging
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def run_single(version_id: str, start: str, end: str, source: str):
    from strategy import load_strategy
    from core.data_fetcher import get_daily_data, get_intraday_data
    from core.journal import save_journal
    from engine.backtest_runner import run

    log.info("═" * 60)
    log.info(f"  Version {version_id}  |  {start} → {end}  |  source={source}")
    log.info("═" * 60)

    strategy = load_strategy(version_id)
    strategy.validate()

    log.info("📥  Fetching daily data…")
    daily = get_daily_data(start=start, end=end, source=source)
    log.info(f"    {len(daily)} daily bars loaded.")

    journal = run(
        strategy=strategy,
        daily_df=daily,
        get_intraday_fn=lambda d: get_intraday_data(trade_date=d, source=source),
        source=source,
    )

    version_dir = save_journal(
        df=journal,
        version=version_id,
        params=strategy.get_params(),
        source=source,
    )

    import pandas as pd
    trades = journal[journal["entry_type"].isin(["ORIGINAL", "RE-ENTRY"])]
    pnl    = pd.to_numeric(trades["total_pnl_pts"], errors="coerce")
    wins   = trades["trade_outcome"].str.startswith("WIN", na=False)

    log.info("─" * 50)
    log.info(f"  Version : {version_id}")
    log.info(f"  Trades  : {len(trades)}")
    if len(trades):
        log.info(f"  P&L     : {pnl.sum():+.1f} pts")
        log.info(f"  Win     : {wins.mean()*100:.1f}%")
    log.info(f"  Saved   → {version_dir}")
    log.info("─" * 50 + "\n")


def main():
    from strategy import all_versions, minor_versions_of

    parser = argparse.ArgumentParser(description="CPR Strategy Backtest Runner")

    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--version", metavar="M.N",
                     help="Single version e.g. --version 1.1")
    grp.add_argument("--major",   metavar="M",
                     help="All minors of one major e.g. --major 1")
    grp.add_argument("--all",     action="store_true",
                     help="Run every discovered version")

    parser.add_argument("--source", default="auto",
                        choices=["auto", "kite", "yfinance"])
    parser.add_argument("--start",
                        default=os.getenv("BACKTEST_START", "2015-01-01"))
    parser.add_argument("--end",
                        default=os.getenv("BACKTEST_END", "2026-02-28"))
    args = parser.parse_args()

    if args.all:
        versions = all_versions()
    elif args.major:
        versions = minor_versions_of(args.major)
        if not versions:
            log.error(f"No versions found for major '{args.major}'")
            sys.exit(1)
    elif args.version:
        versions = [args.version]
    else:
        parser.print_help()
        sys.exit(0)

    log.info(f"🚀  Running {len(versions)} version(s): {versions}")

    failed = []
    for v in versions:
        try:
            run_single(v, args.start, args.end, args.source)
        except Exception as e:
            log.error(f"❌  Version {v} failed: {e}")
            failed.append(v)
            if len(versions) == 1:
                sys.exit(1)

    if failed:
        log.warning(f"⚠  Failed: {failed}")
    else:
        log.info("✅  All done.")
    log.info("    Launch dashboard:  streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
