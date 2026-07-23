"""Benchmark dataset size, key query execution times, fraud-rule execution time, and
ingestion duration. Results feed docs/performance.md.

Usage:
    python scripts/benchmark.py
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Neo4jConnection  # noqa: E402
from app.repositories.investigation_repository import InvestigationRepository  # noqa: E402
from app.services.fraud_detection_service import FraudDetectionService  # noqa: E402

T = TypeVar("T")


def timed(fn: Callable[[], T]) -> tuple[T, float]:
    start = time.perf_counter()
    result = fn()
    duration_ms = (time.perf_counter() - start) * 1000
    return result, duration_ms


def main() -> None:
    connection = Neo4jConnection()
    connection.connect()
    repo = InvestigationRepository(connection)

    dataset_size = {
        "customers": connection.run_query("MATCH (c:Customer) RETURN count(c) AS n")[0]["n"],
        "accounts": connection.run_query("MATCH (a:Account) RETURN count(a) AS n")[0]["n"],
        "transactions": connection.run_query("MATCH (t:Transaction) RETURN count(t) AS n")[0]["n"],
    }

    queries = {
        "find_devices_shared_by_many_customers": lambda: repo.find_devices_shared_by_many_customers(5),
        "find_ips_shared_by_many_customers": lambda: repo.find_ips_shared_by_many_customers(5),
        "find_circular_transfers": lambda: repo.find_circular_transfers(),
        "find_rapid_pass_through_accounts": lambda: repo.find_rapid_pass_through_accounts(),
        "find_fan_in_accounts": lambda: repo.find_fan_in_accounts(),
        "find_fan_out_accounts": lambda: repo.find_fan_out_accounts(),
        "find_structuring_transactions": lambda: repo.find_structuring_transactions(),
        "list_flagged_transactions": lambda: repo.list_flagged_transactions(limit=25),
    }

    query_results = {}
    for name, fn in queries.items():
        result, duration_ms = timed(fn)
        query_results[name] = {"duration_ms": round(duration_ms, 1), "records_returned": len(result)}

    detection_service = FraudDetectionService(connection)
    detection_summary, detection_ms = timed(detection_service.run_all)

    connection.close()

    report = {
        "dataset_size": dataset_size,
        "query_benchmarks": query_results,
        "fraud_rule_execution": {
            "total_duration_ms": round(detection_ms, 1),
            "signals_per_rule": detection_summary["signals_per_rule"],
            "alerts_created": detection_summary["alerts_created"],
        },
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
