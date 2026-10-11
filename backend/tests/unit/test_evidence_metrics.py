from budgeted_research.domain.models import EvidenceItem
from budgeted_research.evidence.metrics import EvidenceMetricsEvaluator


def _item(identifier: str, claim: str, source_id: str) -> EvidenceItem:
    return EvidenceItem(
        id=identifier,
        subquestion_id="sq_01",
        claim=claim,
        support_span=claim,
        source_id=source_id,
        source_url=f"https://example.com/{source_id}",
        source_title=source_id,
    )


def test_metrics_measure_novelty_coverage_and_source_diversity() -> None:
    evaluator = EvidenceMetricsEvaluator(target_claims=2, target_sources=2)
    existing = [_item("ev_01", "Feature is available", "src_01")]
    candidates = [
        _item("ev_duplicate", "Feature is available", "src_01"),
        _item("ev_02", "Feature is stable", "src_02"),
    ]

    accepted, metrics, clusters = evaluator.evaluate(
        existing, candidates, rejected_count=1
    )

    assert [item.id for item in accepted] == ["ev_02"]
    assert metrics.novelty == 1.0
    assert metrics.coverage == 1.0
    assert metrics.source_diversity == 1.0
    assert metrics.rejected_evidence_count == 1
    assert metrics.duplicate_evidence_count == 1
    assert len(clusters) == 2


def test_metrics_detect_opposed_claims_with_shared_subject() -> None:
    evaluator = EvidenceMetricsEvaluator()
    candidates = [
        _item("ev_01", "Feature is available", "src_01"),
        _item("ev_02", "Feature is not available", "src_02"),
    ]

    _, metrics, _ = evaluator.evaluate([], candidates)

    assert metrics.conflict_ratio == 1.0


def test_same_span_is_deduplicated_but_cross_source_claims_are_clustered() -> None:
    evaluator = EvidenceMetricsEvaluator()
    candidates = [
        EvidenceItem(
            id="ev_01",
            subquestion_id="sq_01",
            claim="Python 的 list 是可变的，tuple 是不可变的",
            support_span="Lists are mutable, while tuples are immutable.",
            source_id="src_01",
            source_url="https://example.com/src_01",
            source_title="src_01",
        ),
        EvidenceItem(
            id="ev_02",
            subquestion_id="sq_01",
            claim=(
                "Python 的 list 是可变的（mutable），"
                "而 tuple 是不可变的（immutable）"
            ),
            support_span="Lists are mutable, while tuples are immutable.",
            source_id="src_01",
            source_url="https://example.com/src_01",
            source_title="src_01",
        ),
        EvidenceItem(
            id="ev_03",
            subquestion_id="sq_01",
            claim=(
                "Python 的 list 是可变的（mutable），"
                "而 tuple 是不可变的（immutable）"
            ),
            support_span="A list can be changed; a tuple cannot be changed.",
            source_id="src_02",
            source_url="https://example.com/src_02",
            source_title="src_02",
        ),
    ]

    accepted, metrics, clusters = evaluator.evaluate([], candidates)

    assert [item.id for item in accepted] == ["ev_01", "ev_03"]
    assert metrics.duplicate_evidence_count == 1
    assert metrics.source_count == 2
    assert len(clusters) == 1
    assert clusters[0].evidence_ids == ["ev_01", "ev_03"]


def test_same_source_paraphrases_with_overlapping_support_are_deduplicated() -> None:
    evaluator = EvidenceMetricsEvaluator()
    candidates = [
        EvidenceItem(
            id="ev_01",
            subquestion_id="sq_01",
            claim="Python 的 list 是可变的，tuple 是不可变的",
            support_span=(
                "A list is mutable, which means it can change. "
                "A tuple is immutable, which means it cannot change."
            ),
            source_id="src_01",
            source_url="https://example.com/src_01",
            source_title="src_01",
        ),
        EvidenceItem(
            id="ev_02",
            subquestion_id="sq_01",
            claim="list 是可变的（mutable），tuple 是不可变的（immutable）",
            support_span="A list is mutable. A tuple is immutable.",
            source_id="src_01",
            source_url="https://example.com/src_01",
            source_title="src_01",
        ),
    ]

    accepted, metrics, clusters = evaluator.evaluate([], candidates)

    assert [item.id for item in accepted] == ["ev_01"]
    assert metrics.duplicate_evidence_count == 1
    assert metrics.claim_cluster_count == 1
    assert metrics.novelty == 1.0
    assert len(clusters) == 1


def test_cross_source_mutability_paraphrases_share_one_claim_cluster() -> None:
    evaluator = EvidenceMetricsEvaluator()
    candidates = [
        EvidenceItem(
            id="ev_01",
            subquestion_id="sq_01",
            claim="Python 的 list 是可变的数据类型，而 tuple 是不可变的",
            support_span="Lists are mutable while tuples are immutable.",
            source_id="src_01",
            source_url="https://example.com/src_01",
            source_title="src_01",
        ),
        EvidenceItem(
            id="ev_02",
            subquestion_id="sq_01",
            claim="Python 的 list 是可变的，tuple 是不可变的",
            support_span="A list can change; a tuple cannot change.",
            source_id="src_02",
            source_url="https://example.com/src_02",
            source_title="src_02",
        ),
    ]

    accepted, metrics, clusters = evaluator.evaluate([], candidates)

    assert [item.id for item in accepted] == ["ev_01", "ev_02"]
    assert metrics.evidence_count == 2
    assert metrics.claim_cluster_count == 1
    assert metrics.source_diversity == 1.0
    assert clusters[0].evidence_ids == ["ev_01", "ev_02"]
