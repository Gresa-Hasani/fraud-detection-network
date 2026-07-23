from datetime import UTC, datetime

from app.schemas.fraud import FraudSignal
from app.services.risk_scoring_service import MAX_SCORE, RiskScoringService

NOW = datetime.now(UTC)


def _signal(rule_id: str, entity_id: str, contribution: int, related: list[str] | None = None) -> FraudSignal:
    return FraudSignal(
        rule_id=rule_id,
        rule_name=f"Rule {rule_id}",
        entity_id=entity_id,
        entity_type="Account",
        score_contribution=contribution,
        description=f"{rule_id} triggered",
        related_entity_ids=related or [],
        detected_at=NOW,
    )


def test_single_signal_scores_exactly_its_weight() -> None:
    service = RiskScoringService()
    assessments = service.score_entities([_signal("FD-001", "ACC-1", 15)])
    assert len(assessments) == 1
    assert assessments[0].risk_score == 15
    assert assessments[0].risk_level == "LOW"


def test_multiple_distinct_rules_sum_their_contributions() -> None:
    service = RiskScoringService()
    signals = [_signal("FD-001", "ACC-1", 15), _signal("FD-003", "ACC-1", 30)]
    assessments = service.score_entities(signals)
    assert assessments[0].risk_score == 45
    assert assessments[0].risk_level == "MEDIUM"


def test_repeated_hits_from_the_same_rule_do_not_stack() -> None:
    """Two pieces of evidence for the same rule should contribute once, at their max weight."""
    service = RiskScoringService()
    signals = [_signal("FD-002", "ACC-1", 15), _signal("FD-002", "ACC-1", 25)]
    assessments = service.score_entities(signals)
    assert assessments[0].risk_score == 25
    assert len(assessments[0].reasons) == 1


def test_score_is_capped_at_max_score() -> None:
    service = RiskScoringService()
    signals = [
        _signal("FD-003", "ACC-1", 30),
        _signal("FD-008", "ACC-1", 30),
        _signal("FD-009", "ACC-1", 30),
        _signal("FD-010", "ACC-1", 25),
    ]
    assessments = service.score_entities(signals)
    assert assessments[0].risk_score == MAX_SCORE
    assert assessments[0].risk_level == "CRITICAL"


def test_risk_level_boundaries() -> None:
    service = RiskScoringService()
    cases = [(0, "LOW"), (24, "LOW"), (25, "MEDIUM"), (49, "MEDIUM"), (50, "HIGH"), (74, "HIGH"), (75, "CRITICAL")]
    for score, expected_level in cases:
        assessments = service.score_entities([_signal("FD-001", "ACC-X", score)])
        assert assessments[0].risk_level == expected_level, f"score={score}"


def test_entities_are_scored_independently() -> None:
    service = RiskScoringService()
    signals = [_signal("FD-001", "ACC-1", 15), _signal("FD-001", "ACC-2", 15)]
    assessments = service.score_entities(signals)
    scores_by_entity = {a.entity_id: a.risk_score for a in assessments}
    assert scores_by_entity == {"ACC-1": 15, "ACC-2": 15}


def test_related_entities_are_deduplicated_and_sorted() -> None:
    service = RiskScoringService()
    signals = [
        _signal("FD-001", "ACC-1", 15, related=["ACC-9", "ACC-3"]),
        _signal("FD-003", "ACC-1", 30, related=["ACC-3", "ACC-5"]),
    ]
    assessments = service.score_entities(signals)
    assert assessments[0].related_entities == ["ACC-3", "ACC-5", "ACC-9"]


def test_reasons_are_sorted_by_contribution_descending() -> None:
    service = RiskScoringService()
    signals = [_signal("FD-005", "ACC-1", 15), _signal("FD-003", "ACC-1", 30), _signal("FD-007", "ACC-1", 20)]
    assessments = service.score_entities(signals)
    contributions = [r.score_contribution for r in assessments[0].reasons]
    assert contributions == sorted(contributions, reverse=True)


def test_no_signals_produces_no_assessments() -> None:
    service = RiskScoringService()
    assert service.score_entities([]) == []
