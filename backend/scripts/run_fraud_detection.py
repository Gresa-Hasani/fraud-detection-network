"""Run the full fraud detection rule engine against the currently loaded graph.

Usage:
    python scripts/run_fraud_detection.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Neo4jConnection  # noqa: E402
from app.services.fraud_detection_service import FraudDetectionService  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("run_fraud_detection")


def main() -> None:
    connection = Neo4jConnection()
    connection.connect()
    try:
        service = FraudDetectionService(connection)
        summary = service.run_all()
        print(json.dumps(summary, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
