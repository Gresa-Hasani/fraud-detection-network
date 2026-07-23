"""Combines per-rule fraud signals into an explainable, normalized risk score.

Pure and DB-free by design (takes signals in, returns assessments out) so it
can be unit tested without a live Neo4j instance and reused identically by
both the batch detection job and any future "explain this score" endpoint.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from app.core.fraud_rules_config import risk_level_for_score
from app.schemas.fraud import FraudSignal, RiskAssessment, RiskReason

MAX_SCORE = 100


class RiskScoringService:
    def score_entities(self, signals: list[FraudSignal]) -> list[RiskAssessment]:
        """Group signals by entity, dedupe repeated hits from the same rule, sum, and normalize.

        A rule firing multiple times for the same entity (e.g. two separate pieces of shared-IP
        evidence) contributes its weight once -- the point system rewards *which* risk factors are
        present, not how many times evidence for the same factor was observed.
        """
        by_entity: dict[tuple[str, str], list[FraudSignal]] = defaultdict(list)
        for signal in signals:
            by_entity[(signal.entity_id, signal.entity_type)].append(signal)

        assessments: list[RiskAssessment] = []
        for (entity_id, entity_type), entity_signals in by_entity.items():
            best_per_rule: dict[str, FraudSignal] = {}
            for signal in entity_signals:
                existing = best_per_rule.get(signal.rule_id)
                if existing is None or signal.score_contribution > existing.score_contribution:
                    best_per_rule[signal.rule_id] = signal

            total_score = min(MAX_SCORE, sum(s.score_contribution for s in best_per_rule.values()))
            related_entities = sorted({eid for s in entity_signals for eid in s.related_entity_ids})

            assessments.append(
                RiskAssessment(
                    entity_id=entity_id,
                    entity_type=entity_type,
                    risk_score=total_score,
                    risk_level=risk_level_for_score(total_score),
                    reasons=[
                        RiskReason(
                            rule_id=s.rule_id,
                            rule_name=s.rule_name,
                            score_contribution=s.score_contribution,
                            description=s.description,
                        )
                        for s in sorted(best_per_rule.values(), key=lambda s: -s.score_contribution)
                    ],
                    related_entities=related_entities,
                    calculated_at=datetime.now(UTC),
                )
            )
        return assessments
