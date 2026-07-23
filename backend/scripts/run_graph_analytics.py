"""Run the Neo4j Graph Data Science pipeline (PageRank, WCC, Louvain[, betweenness])
against the currently loaded graph.

Usage:
    python scripts/run_graph_analytics.py [--betweenness]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.graph_analytics_service import GraphAnalyticsService  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--betweenness", action="store_true", help="Also run betweenness centrality (expensive).")
    args = parser.parse_args()

    service = GraphAnalyticsService()
    try:
        summary = service.run_all(include_betweenness=args.betweenness)
        print(json.dumps(summary, indent=2, default=str))
    finally:
        service.close()


if __name__ == "__main__":
    main()
