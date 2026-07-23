"""Runs the configurable rule-based fraud detection engine.

Each `run_fd0xx` method evaluates one rule against the graph and returns a
list of `FraudSignal`s -- it never writes to the database itself. `run_all`
orchestrates every rule, feeds the combined signals through
`RiskScoringService` to get one explainable score per entity, and persists
both the alerts and the scores via `FraudRepository`. This separation is
what makes the rules unit-testable (pure evidence -> signal mapping) and the
persistence idempotent (`FraudRepository.upsert_alert` MERGEs on a
deterministic alert id).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings, get_settings
from app.core.database import Neo4jConnection
from app.core.fraud_rules_config import PROXIMITY_WEIGHTS_BY_HOP, RULES
from app.repositories.fraud_repository import FraudRepository
from app.repositories.investigation_repository import InvestigationRepository
from app.schemas.fraud import FraudSignal, RiskAssessment
from app.services.risk_scoring_service import RiskScoringService

logger = logging.getLogger("app.fraud_detection")

MAX_PROXIMITY_CHECKS = 500


class FraudDetectionService:
    def __init__(self, connection: Neo4jConnection, settings: Settings | None = None) -> None:
        self._db = connection
        self._settings = settings or get_settings()
        self._investigations = InvestigationRepository(connection)
        self._fraud_repo = FraudRepository(connection)
        self._scorer = RiskScoringService()

    # ------------------------------------------------------------------
    # Individual rules -- pure evidence-gathering, return signals only.
    # ------------------------------------------------------------------

    def run_fd001_shared_device(self) -> list[FraudSignal]:
        rule = RULES["FD-001"]
        now = datetime.now(UTC)
        signals: list[FraudSignal] = []
        for row in self._investigations.find_devices_shared_by_many_customers(
            self._settings.default_shared_device_min_customers
        ):
            bonus = (10 if row["is_emulator"] else 0) + (10 if row["is_rooted"] else 0)
            contribution = rule.weight + bonus
            reason = (
                f"Device is shared by {row['customer_count']} unrelated customers"
                f"{' (emulator)' if row['is_emulator'] else ''}{' (rooted)' if row['is_rooted'] else ''}."
            )
            evidence = {"customer_count": row["customer_count"], "customers": row["customers"]}
            signals.append(
                FraudSignal(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    entity_id=row["device_id"],
                    entity_type="Device",
                    score_contribution=contribution,
                    description=reason,
                    evidence=evidence,
                    related_entity_ids=row["customers"],
                    detected_at=now,
                )
            )
            for account_id in self._account_ids_for_customers(row["customers"]):
                signals.append(
                    FraudSignal(
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        entity_id=account_id,
                        entity_type="Account",
                        score_contribution=contribution,
                        description=reason,
                        evidence=evidence,
                        related_entity_ids=[row["device_id"]],
                        detected_at=now,
                    )
                )
        return signals

    def run_fd002_shared_ip(self) -> list[FraudSignal]:
        rule = RULES["FD-002"]
        now = datetime.now(UTC)
        signals: list[FraudSignal] = []
        for row in self._investigations.find_ips_shared_by_many_customers(
            self._settings.default_shared_ip_min_customers
        ):
            bonus = 10 if (row["is_vpn"] or row["is_proxy"] or row["is_tor"]) else 0
            contribution = rule.weight + bonus
            reason = f"IP {row['ip']} is shared by {row['customer_count']} unrelated customers."
            evidence = {"customer_count": row["customer_count"], "customers": row["customers"]}
            signals.append(
                FraudSignal(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    entity_id=row["ip"],
                    entity_type="IPAddress",
                    score_contribution=contribution,
                    description=reason,
                    evidence=evidence,
                    related_entity_ids=row["customers"],
                    detected_at=now,
                )
            )
            for account_id in self._account_ids_for_customers(row["customers"]):
                signals.append(
                    FraudSignal(
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        entity_id=account_id,
                        entity_type="Account",
                        score_contribution=contribution,
                        description=reason,
                        evidence=evidence,
                        related_entity_ids=[row["ip"]],
                        detected_at=now,
                    )
                )
        return signals

    def run_fd003_circular_transfer(self) -> list[FraudSignal]:
        rule = RULES["FD-003"]
        now = datetime.now(UTC)
        signals: list[FraudSignal] = []
        for cycle in self._investigations.find_circular_transfers(
            window_hours=self._settings.default_cycle_time_window_hours,
            amount_tolerance_pct=self._settings.default_cycle_amount_tolerance_pct,
        ):
            members = cycle["account_cycle"][:-1]
            reason = f"Account participates in a {cycle['cycle_length']}-account transaction cycle."
            for account_id in members:
                signals.append(
                    FraudSignal(
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        entity_id=account_id,
                        entity_type="Account",
                        score_contribution=rule.weight,
                        description=reason,
                        evidence={"transaction_ids": cycle["transaction_ids"], "cycle_length": cycle["cycle_length"]},
                        related_entity_ids=[a for a in members if a != account_id],
                        detected_at=now,
                    )
                )
        return signals

    def run_fd004_rapid_pass_through(self) -> list[FraudSignal]:
        rule = RULES["FD-004"]
        now = datetime.now(UTC)
        signals: list[FraudSignal] = []
        for row in self._investigations.find_rapid_pass_through_accounts(
            max_minutes=self._settings.default_rapid_pass_through_minutes,
            min_forwarded_pct=self._settings.default_rapid_pass_through_min_pct,
        ):
            reason = (
                f"Received {row['inbound_amount']:.2f} and forwarded {row['outbound_amount']:.2f} "
                f"within {row['seconds_between'] // 60} minutes."
            )
            signals.append(
                FraudSignal(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    entity_id=row["account_id"],
                    entity_type="Account",
                    score_contribution=rule.weight,
                    description=reason,
                    evidence={k: row[k] for k in ("inbound_transaction_id", "outbound_transaction_id")},
                    related_entity_ids=[row["inbound_transaction_id"], row["outbound_transaction_id"]],
                    detected_at=now,
                )
            )
        return signals

    def run_fd005_fan_in(self) -> list[FraudSignal]:
        rule = RULES["FD-005"]
        now = datetime.now(UTC)
        signals: list[FraudSignal] = []
        for row in self._investigations.find_fan_in_accounts(
            min_sources=self._settings.default_fan_in_min_sources, window_hours=self._settings.default_fan_window_hours
        ):
            reason = f"Received transfers from {row['source_count']} distinct accounts in a short window."
            related = [s["source"] for s in row["sources"]]
            signals.append(
                FraudSignal(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    entity_id=row["account_id"],
                    entity_type="Account",
                    score_contribution=rule.weight,
                    description=reason,
                    evidence={"source_count": row["source_count"]},
                    related_entity_ids=related,
                    detected_at=now,
                )
            )
        return signals

    def run_fd006_fan_out(self) -> list[FraudSignal]:
        rule = RULES["FD-006"]
        now = datetime.now(UTC)
        signals: list[FraudSignal] = []
        for row in self._investigations.find_fan_out_accounts(
            min_targets=self._settings.default_fan_out_min_targets, window_hours=self._settings.default_fan_window_hours
        ):
            reason = f"Sent transfers to {row['target_count']} distinct accounts in a short window."
            related = [t["target"] for t in row["targets"]]
            signals.append(
                FraudSignal(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    entity_id=row["account_id"],
                    entity_type="Account",
                    score_contribution=rule.weight,
                    description=reason,
                    evidence={"target_count": row["target_count"]},
                    related_entity_ids=related,
                    detected_at=now,
                )
            )
        return signals

    def run_fd007_structuring(self) -> list[FraudSignal]:
        rule = RULES["FD-007"]
        now = datetime.now(UTC)
        signals: list[FraudSignal] = []
        for row in self._investigations.find_structuring_transactions(
            threshold=self._settings.default_structuring_threshold,
            margin_pct=self._settings.default_structuring_margin_pct,
            window_hours=self._settings.default_structuring_window_hours,
        ):
            reason = (
                f"{row['occurrence_count']} transfers just below the "
                f"{self._settings.default_structuring_threshold:.0f} reporting threshold in a short window."
            )
            tx_ids = [tx["transaction_id"] for tx in row["below_threshold_txs"]]
            signals.append(
                FraudSignal(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    entity_id=row["account_id"],
                    entity_type="Account",
                    score_contribution=rule.weight,
                    description=reason,
                    evidence={"occurrence_count": row["occurrence_count"]},
                    related_entity_ids=tx_ids,
                    detected_at=now,
                )
            )
        return signals

    def run_fd008_account_takeover(self) -> list[FraudSignal]:
        rule = RULES["FD-008"]
        now = datetime.now(UTC)
        signals: list[FraudSignal] = []
        for row in self._investigations.find_account_takeover_candidates():
            reasons = []
            if row.get("is_vpn") or row.get("is_proxy") or row.get("is_tor"):
                reasons.append("anonymized IP (VPN/proxy/Tor)")
            if row.get("ip_country") and row.get("customer_country") and row["ip_country"] != row["customer_country"]:
                reasons.append(f"IP country {row['ip_country']} != customer country {row['customer_country']}")
            reason = (
                f"High-value transaction ({row['amount']:.2f}) from a new device at an unusual hour, "
                f"with {' and '.join(reasons) or 'an anomalous IP'}."
            )
            signals.append(
                FraudSignal(
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    entity_id=row["account_id"],
                    entity_type="Account",
                    score_contribution=rule.weight,
                    description=reason,
                    evidence={"transaction_id": row["transaction_id"], "amount": row["amount"]},
                    related_entity_ids=[row["device_id"], row.get("ip") or ""],
                    detected_at=now,
                )
            )
        return signals

    def run_fd009_fraud_proximity(self, candidate_customer_ids: set[str]) -> list[FraudSignal]:
        rule_id, rule_name = "FD-009", RULES["FD-009"].name
        now = datetime.now(UTC)
        signals: list[FraudSignal] = []

        candidates = list(candidate_customer_ids)[:MAX_PROXIMITY_CHECKS]
        hops_by_customer = self._investigations.find_shortest_paths_to_confirmed_fraud_batch(candidates, max_hops=3)
        if not hops_by_customer:
            return signals

        accounts_by_customer = self._accounts_by_customer(list(hops_by_customer.keys()))
        for customer_id, hops in hops_by_customer.items():
            weight = PROXIMITY_WEIGHTS_BY_HOP.get(hops)
            if weight is None:
                continue
            reason = f"{hops}-hop connection to a confirmed fraud customer."
            for account_id in accounts_by_customer.get(customer_id, []):
                signals.append(
                    FraudSignal(
                        rule_id=rule_id,
                        rule_name=rule_name,
                        entity_id=account_id,
                        entity_type="Account",
                        score_contribution=weight,
                        description=reason,
                        evidence={"hops": hops},
                        related_entity_ids=[],
                        detected_at=now,
                    )
                )
        return signals

    def run_fd010_suspicious_community(self) -> list[FraudSignal]:
        rule = RULES["FD-010"]
        now = datetime.now(UTC)
        signals: list[FraudSignal] = []
        for row in self._investigations.find_suspicious_communities():
            reason = (
                f"Member of community {row['community_id']} ({row['member_count']} accounts, "
                f"{row['critical_member_count']} critical-risk)."
            )
            for account_id in row["account_ids"]:
                signals.append(
                    FraudSignal(
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        entity_id=account_id,
                        entity_type="Account",
                        score_contribution=rule.weight,
                        description=reason,
                        evidence={"community_id": row["community_id"], "member_count": row["member_count"]},
                        related_entity_ids=[a for a in row["account_ids"] if a != account_id],
                        detected_at=now,
                    )
                )
        return signals

    # ------------------------------------------------------------------
    # Orchestration
    # ------------------------------------------------------------------

    def persist_signals(self, signals: list[FraudSignal]) -> int:
        """Upsert alerts for a set of signals (e.g. from a single ad hoc rule run). Returns the
        number newly created."""
        return self._fraud_repo.upsert_alerts_batch(signals)

    def run_all(self) -> dict[str, Any]:
        started = time.perf_counter()
        rule_runners = [
            self.run_fd001_shared_device,
            self.run_fd002_shared_ip,
            self.run_fd003_circular_transfer,
            self.run_fd004_rapid_pass_through,
            self.run_fd005_fan_in,
            self.run_fd006_fan_out,
            self.run_fd007_structuring,
            self.run_fd008_account_takeover,
            self.run_fd010_suspicious_community,
        ]

        all_signals: list[FraudSignal] = []
        per_rule_counts: dict[str, int] = {}
        for runner in rule_runners:
            rule_started = time.perf_counter()
            signals = runner()
            all_signals.extend(signals)
            per_rule_counts[runner.__name__] = len(signals)
            logger.info(
                "rule=%s signals=%d duration_ms=%.1f",
                runner.__name__,
                len(signals),
                (time.perf_counter() - rule_started) * 1000,
            )

        flagged_account_ids = list({s.entity_id for s in all_signals if s.entity_type == "Account"})
        proximity_candidates = set(self._customers_for_accounts(flagged_account_ids).values())
        fd009_signals = self.run_fd009_fraud_proximity(proximity_candidates)
        all_signals.extend(fd009_signals)
        per_rule_counts["run_fd009_fraud_proximity"] = len(fd009_signals)

        assessments = self._scorer.score_entities(all_signals)

        alerts_created = self._fraud_repo.upsert_alerts_batch(all_signals)
        self._fraud_repo.apply_risk_assessments_batch(assessments)

        duration = time.perf_counter() - started
        summary = {
            "duration_seconds": round(duration, 2),
            "signals_per_rule": per_rule_counts,
            "total_signals": len(all_signals),
            "entities_scored": len(assessments),
            "alerts_created": alerts_created,
        }
        logger.info("fraud_detection_run_complete %s", summary)
        return summary

    def assess_entity(self, entity_id: str, entity_type: str) -> RiskAssessment | None:
        """Recompute a single entity's assessment from the signals currently stored on it.

        Used by the API's "why does this account have this score" endpoint -- reads back the
        FraudAlert evidence already persisted rather than re-running every rule synchronously.
        """
        assessments = self._scorer.score_entities(self._signals_from_existing_alerts(entity_id, entity_type))
        return assessments[0] if assessments else None

    _ENTITY_ID_FIELDS = {"Account": "account_id", "Customer": "customer_id", "Device": "device_id", "IPAddress": "ip"}

    def _signals_from_existing_alerts(self, entity_id: str, entity_type: str) -> list[FraudSignal]:
        id_field = self._ENTITY_ID_FIELDS.get(entity_type, "account_id")
        rows = self._db.run_query(
            f"""
            MATCH (alert:FraudAlert)-[:ALERTS_ON]->(entity {{{id_field}: $entity_id}})
            RETURN alert
            """,
            {"entity_id": entity_id},
        )
        now = datetime.now(UTC)
        signals = []
        for row in rows:
            alert = row["alert"]
            rule_id = alert.get("rule_id", alert.get("alert_type", "UNKNOWN"))
            signals.append(
                FraudSignal(
                    rule_id=rule_id,
                    rule_name=RULES[rule_id].name if rule_id in RULES else rule_id,
                    entity_id=entity_id,
                    entity_type=entity_type,
                    score_contribution=alert.get("score", 0),
                    description=alert.get("description", ""),
                    evidence={},
                    related_entity_ids=[],
                    detected_at=now,
                )
            )
        return signals

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _account_ids_for_customers(self, customer_ids: list[str]) -> list[str]:
        if not customer_ids:
            return []
        rows = self._db.run_query(
            "MATCH (c:Customer)-[:OWNS]->(a:Account) WHERE c.customer_id IN $ids RETURN a.account_id AS account_id",
            {"ids": customer_ids},
        )
        return [row["account_id"] for row in rows]

    def _customers_for_accounts(self, account_ids: list[str]) -> dict[str, str]:
        """account_id -> owning customer_id, batched in a single round trip."""
        if not account_ids:
            return {}
        rows = self._db.run_query(
            """
            MATCH (c:Customer)-[:OWNS]->(a:Account)
            WHERE a.account_id IN $account_ids
            RETURN a.account_id AS account_id, c.customer_id AS customer_id
            """,
            {"account_ids": account_ids},
        )
        return {row["account_id"]: row["customer_id"] for row in rows}

    def _accounts_by_customer(self, customer_ids: list[str]) -> dict[str, list[str]]:
        """customer_id -> owned account_ids, batched in a single round trip."""
        if not customer_ids:
            return {}
        rows = self._db.run_query(
            """
            MATCH (c:Customer)-[:OWNS]->(a:Account)
            WHERE c.customer_id IN $customer_ids
            RETURN c.customer_id AS customer_id, a.account_id AS account_id
            """,
            {"customer_ids": customer_ids},
        )
        grouped: dict[str, list[str]] = defaultdict(list)
        for row in rows:
            grouped[row["customer_id"]].append(row["account_id"])
        return grouped
