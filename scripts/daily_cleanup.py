#!/usr/bin/env python3
"""Daily cleanup runner script for GraphCortex.

Purges expired/stale guest user authentication records, session logs,
and FalkorDB guest graph nodes/dead graphs older than 2 days.
"""

import argparse
import json
import sys

from graph_intelligence.common.logging_setup import get_logger
from graph_intelligence.remote.cleanup import cleanup_stale_records_and_graphs

logger = get_logger("daily_cleanup_script")


def main():
    parser = argparse.ArgumentParser(description="Run GraphCortex daily cleanup of stale records and graphs.")
    parser.add_argument(
        "--days",
        type=int,
        default=2,
        help="Age in days beyond which records are considered dead/stale (default: 2)",
    )
    args = parser.parse_args()

    print(f"[INFO] Initiating daily cleanup job for records older than {args.days} days...")
    res = cleanup_stale_records_and_graphs(days=args.days)
    print(f"[SUCCESS] Cleanup completed successfully.")
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
