"""Evaluate rule-based fraud detection against the synthetic dataset's ground truth.

For each rule, compares the accounts currently holding an open FraudAlert for that rule
against the accounts the generator planted for the matching fraud scenario, and reports
precision / recall / F1. This is a real evaluation against known-imperfect ground truth --
scores are not expected to hit 1.0 (see docs/performance.md and README limitations): rules
like FD-002 (shared IP) will legitimately catch real, non-planted IP-sharing coincidences,
which count as false positives here exactly as they would for a fraud analyst.

Usage:
    python scripts/evaluate_detection.py [--ground-truth ../data/generated/fraud_ground_truth.csv]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Neo4jConnection  # noqa: E402

# FD-010 (suspicious community) has no single matching scenario -- community membership is a
# cross-cutting signal over accounts planted by every other scenario -- so it's excluded here.
RULE_TO_SCENARIO = {
    "FD-001": "SHARED_DEVICE_RING",
    "FD-002": "SHARED_IP",
    "FD-003": "CIRCULAR_TRANSFER",
    "FD-004": "RAPID_PASS_THROUGH",
    "FD-005": "FAN_IN",
    "FD-006": "FAN_OUT",
    "FD-007": "STRUCTURING",
    "FD-008": "ACCOUNT_TAKEOVER",
}


def load_ground_truth(path: Path) -> dict[str, set[str]]:
    """rule_id -> set of account_ids the generator planted for that rule's scenario."""
    by_scenario: dict[str, set[str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["entity_type"] != "Account":
                continue
            by_scenario.setdefault(row["fraud_scenario"], set()).add(row["entity_id"])

    result: dict[str, set[str]] = {}
    for rule_id, scenario in RULE_TO_SCENARIO.items():
        result[rule_id] = by_scenario.get(scenario, set())
    return result


def predicted_accounts_by_rule(connection: Neo4jConnection) -> dict[str, set[str]]:
    rows = connection.run_query(
        "MATCH (alert:FraudAlert)-[:ALERTS_ON]->(a:Account) RETURN alert.rule_id AS rule_id, a.account_id AS account_id"
    )
    result: dict[str, set[str]] = {}
    for row in rows:
        result.setdefault(row["rule_id"], set()).add(row["account_id"])
    return result


def score(expected: set[str], predicted: set[str]) -> dict[str, float | int]:
    tp = len(expected & predicted)
    fp = len(predicted - expected)
    fn = len(expected - predicted)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1_score": round(f1, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--ground-truth",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "generated" / "fraud_ground_truth.csv",
    )
    args = parser.parse_args()

    if not args.ground_truth.exists():
        print(f"Ground truth file not found: {args.ground_truth}", file=sys.stderr)
        sys.exit(1)

    expected_by_rule = load_ground_truth(args.ground_truth)

    connection = Neo4jConnection()
    connection.connect()
    try:
        predicted_by_rule = predicted_accounts_by_rule(connection)
    finally:
        connection.close()

    report = []
    for rule_id, scenario in RULE_TO_SCENARIO.items():
        expected = expected_by_rule.get(rule_id, set())
        predicted = predicted_by_rule.get(rule_id, set())
        metrics = score(expected, predicted)
        report.append({"rule_id": rule_id, "scenario": scenario, **metrics})

    print(json.dumps(report, indent=2))

    print("\nrule    scenario              precision  recall  f1")
    for r in report:
        print(f"{r['rule_id']}  {r['scenario']:<20}  {r['precision']:<9} {r['recall']:<7} {r['f1_score']}")


if __name__ == "__main__":
    main()
