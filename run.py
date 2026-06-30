import argparse
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


BACKEND_DIR = Path(__file__).parent
ROOT_DIR = BACKEND_DIR


if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
try:
    from dotenv import load_dotenv
    env_path = BACKEND_DIR / ".env"
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass  # python-dotenv is optional; export env vars manually if needed

import os
from config.logger import get_logger
logger = get_logger(__name__)

import sentry_sdk
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=1.0,
        _experiments={
            "continuous_profiling_auto_start": True,
        },
    )

from graph.graph import graph


def today_ist() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(
        description="AgentWire LangGraph Article Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
  # Generate today's article (IST):
  python run.py

  # Generate for a specific date:
  python run.py --date 2026-03-07

  # Dry run — no LLM calls, no file writes:
  python run.py --dry-run
        """,
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Target date in YYYY-MM-DD format (default: today in IST)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview mode: skip Groq calls and file writes",
    )
    parser.add_argument(
        "--ainews", action="store_true",
        help="Run the AI News gathering and generation graph",
    )
    args = parser.parse_args()

    date_str = args.date or today_ist()
    dry_run  = args.dry_run
    run_ainews = args.ainews


    logger.info("=======================================================")
    logger.info("  AgentWire — LangGraph Article Generator")
    logger.info(f"  Date    : {date_str}")
    logger.info(f"  Dry run : {dry_run}")
    logger.info("=======================================================")

    
    initial_state = {
        "date":    date_str,
        "dry_run": dry_run,
    }
    
    if run_ainews:
        initial_state["domain"] = "ainews"

    config = {"configurable": {"thread_id": "agentwire-run-thread"}}
    final_state = graph.invoke(initial_state, config=config)

    
    logger.info("=======================================================")
    if dry_run:
        logger.info("[DRY RUN] Pipeline completed — no files were written.")
        domain = final_state.get("domain", "?")
        topic  = final_state.get("topic", "?")
        slug   = final_state.get("slug", "?")
        logger.info(f"  Chosen Domain : {domain}")
        logger.info(f"  Chosen Topic  : {topic}")
        logger.info("  Would have saved to database:")
        logger.info(f"    -> db://articles/{slug}")
    else:
        domain    = final_state.get("domain", "?")
        title     = final_state.get("title", "?")
        md_path   = final_state.get("md_path", "?")
        read_time = final_state.get("read_time", "?")
        logger.info("  🎉 Done!  Article generated successfully.")
        logger.info(f"  Title     : {title}")
        logger.info(f"  Domain    : {domain}")
        logger.info(f"  Read time : {read_time}")
        logger.info(f"  File      : {md_path}")
    logger.info("=======================================================")

if __name__ == "__main__":
    main()
