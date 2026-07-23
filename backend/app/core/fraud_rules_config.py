"""Fraud rule identifiers, score weights, and default thresholds.

Weights and thresholds live here -- not scattered as magic numbers across
route handlers or buried in Cypher -- so the whole scoring model can be
reviewed and tuned in one place. `RiskScoringService` and
`FraudDetectionService` both import from this module rather than
hard-coding values.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    name: str
    description: str
    weight: int


# Base score contribution per triggered rule (see docs/fraud-rules.md for the full rationale).
# FD-009 (fraud proximity) does not use a flat weight -- its contribution depends on hop distance,
# see PROXIMITY_WEIGHTS_BY_HOP below.
RULES: dict[str, RuleDefinition] = {
    "FD-001": RuleDefinition("FD-001", "Shared Device", "Device used by many unrelated customers.", 15),
    "FD-002": RuleDefinition("FD-002", "Shared IP", "IP address used by many unrelated customers.", 15),
    "FD-003": RuleDefinition("FD-003", "Circular Transfer", "Account participates in a closed transfer cycle.", 30),
    "FD-004": RuleDefinition("FD-004", "Rapid Pass-Through", "Account forwards received funds almost immediately.", 20),
    "FD-005": RuleDefinition("FD-005", "Fan-In", "Account receives from many distinct sources quickly.", 15),
    "FD-006": RuleDefinition("FD-006", "Fan-Out", "Account sends to many distinct destinations quickly.", 15),
    "FD-007": RuleDefinition("FD-007", "Structuring", "Multiple transfers just below a reporting threshold.", 20),
    "FD-008": RuleDefinition(
        "FD-008", "Account Takeover", "New device/IP plus high-value transaction at an odd hour.", 30
    ),
    "FD-009": RuleDefinition("FD-009", "Fraud Proximity", "Short graph distance to a confirmed fraud entity.", 0),
    "FD-010": RuleDefinition("FD-010", "Suspicious Community", "Member of a high-risk detected community.", 25),
}

PROXIMITY_WEIGHTS_BY_HOP: dict[int, int] = {1: 30, 2: 20, 3: 10}

RISK_LEVEL_THRESHOLDS: list[tuple[int, str]] = [
    (75, "CRITICAL"),
    (50, "HIGH"),
    (25, "MEDIUM"),
    (0, "LOW"),
]


def risk_level_for_score(score: int) -> str:
    for threshold, level in RISK_LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return "LOW"
