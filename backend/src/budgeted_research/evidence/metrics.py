from __future__ import annotations

import re

from budgeted_research.context.tokenization import tokenize
from budgeted_research.domain.models import ClaimCluster, EvidenceItem, EvidenceMetrics

_CJK_NEGATION_MARKERS = {
    "不",
    "无",
    "未",
    "不能",
    "不是",
    "没有",
}
_ENGLISH_NEGATION_MARKERS = {
    "not",
    "no",
    "never",
    "cannot",
    "without",
}
_CLAIM_STOPWORDS = {
    "的",
    "是",
    "而",
    "了",
    "和",
    "与",
    "the",
    "a",
    "an",
    "is",
    "are",
}


class EvidenceMetricsEvaluator:
    """Deterministic V1 evidence signals used by both policies and evaluation."""

    def __init__(
        self,
        *,
        target_claims: int = 3,
        target_sources: int = 2,
        low_novelty_threshold: float = 0.25,
        claim_similarity_threshold: float = 0.55,
        same_source_claim_similarity_threshold: float = 0.55,
        same_source_support_overlap_threshold: float = 0.8,
        conflict_similarity_threshold: float = 0.45,
    ) -> None:
        self.target_claims = target_claims
        self.target_sources = target_sources
        self.low_novelty_threshold = low_novelty_threshold
        self.claim_similarity_threshold = claim_similarity_threshold
        self.same_source_claim_similarity_threshold = (
            same_source_claim_similarity_threshold
        )
        self.same_source_support_overlap_threshold = (
            same_source_support_overlap_threshold
        )
        self.conflict_similarity_threshold = conflict_similarity_threshold

    def evaluate(
        self,
        existing: list[EvidenceItem],
        candidates: list[EvidenceItem],
        previous: EvidenceMetrics | None = None,
        rejected_count: int = 0,
    ) -> tuple[list[EvidenceItem], EvidenceMetrics, list[ClaimCluster]]:
        known_items = list(existing)
        accepted: list[EvidenceItem] = []
        duplicate_count = 0
        for item in candidates:
            if self._is_same_source_duplicate(item, known_items):
                duplicate_count += 1
                continue
            known_items.append(item)
            accepted.append(item)

        combined = [*existing, *accepted]
        existing_clusters = self._cluster_claims(existing)
        candidate_clusters = self._cluster_claims(accepted)
        combined_clusters = self._cluster_claims(combined)
        unique_sources = {item.source_id for item in combined}
        quality_by_source = {
            item.source_id: item.source_quality.score for item in combined
        }
        existing_sources = {item.source_id for item in existing}
        candidate_sources = {item.source_id for item in accepted}
        new_claim_count = sum(
            not self._matches_cluster(cluster.canonical_claim, existing_clusters)
            for cluster in candidate_clusters
        )
        claim_novelty = (
            new_claim_count / len(candidate_clusters) if candidate_clusters else 0.0
        )
        source_novelty = (
            len(candidate_sources - existing_sources) / len(candidate_sources)
            if candidate_sources
            else 0.0
        )
        novelty = 0.75 * claim_novelty + 0.25 * source_novelty
        evidence_coverage = min(len(combined_clusters) / self.target_claims, 1.0)
        source_diversity = min(len(unique_sources) / self.target_sources, 1.0)
        source_quality_score = (
            sum(quality_by_source.values()) / len(quality_by_source)
            if quality_by_source
            else 0.0
        )
        coverage = 0.7 * evidence_coverage + 0.3 * source_diversity
        conflict_ratio = self._conflict_ratio(combined_clusters)
        previous_streak = previous.low_novelty_streak if previous else 0
        low_novelty_streak = (
            previous_streak + 1
            if novelty < self.low_novelty_threshold
            else 0
        )
        metrics = EvidenceMetrics(
            evidence_count=len(combined),
            claim_cluster_count=len(combined_clusters),
            duplicate_evidence_count=(
                (previous.duplicate_evidence_count if previous else 0)
                + duplicate_count
            ),
            rejected_evidence_count=(
                (previous.rejected_evidence_count if previous else 0)
                + rejected_count
            ),
            source_count=len(unique_sources),
            coverage=round(coverage, 4),
            novelty=round(novelty, 4),
            source_diversity=round(source_diversity, 4),
            source_quality_score=round(source_quality_score, 4),
            conflict_ratio=round(conflict_ratio, 4),
            low_novelty_streak=low_novelty_streak,
        )
        return accepted, metrics, combined_clusters

    def _is_same_source_duplicate(
        self, candidate: EvidenceItem, known_items: list[EvidenceItem]
    ) -> bool:
        for known in known_items:
            if candidate.source_id != known.source_id:
                continue
            if _evidence_key(candidate) == _evidence_key(known):
                return True
            same_polarity = _is_negative(candidate.claim) == _is_negative(known.claim)
            if (
                same_polarity
                and _claim_similarity(candidate.claim, known.claim)
                >= self.same_source_claim_similarity_threshold
            ):
                return True
            if (
                _support_overlap(candidate.support_span, known.support_span)
                >= self.same_source_support_overlap_threshold
            ):
                return True
        return False

    def _cluster_claims(self, evidence: list[EvidenceItem]) -> list[ClaimCluster]:
        clusters: list[ClaimCluster] = []
        for item in evidence:
            matching = next(
                (
                    cluster
                    for cluster in clusters
                    if _is_negative(item.claim)
                    == _is_negative(cluster.canonical_claim)
                    and _claim_similarity(item.claim, cluster.canonical_claim)
                    >= self.claim_similarity_threshold
                ),
                None,
            )
            if matching is None:
                clusters.append(
                    ClaimCluster(
                        id=f"claim_{len(clusters) + 1:02d}",
                        canonical_claim=item.claim,
                        evidence_ids=[item.id],
                    )
                )
            elif item.id not in matching.evidence_ids:
                matching.evidence_ids.append(item.id)
        return clusters

    def _matches_cluster(self, claim: str, clusters: list[ClaimCluster]) -> bool:
        return any(
            _is_negative(claim) == _is_negative(cluster.canonical_claim)
            and _claim_similarity(claim, cluster.canonical_claim)
            >= self.claim_similarity_threshold
            for cluster in clusters
        )

    def _conflict_ratio(self, clusters: list[ClaimCluster]) -> float:
        comparable_pairs = 0
        conflicting_pairs = 0
        for index, left in enumerate(clusters):
            for right in clusters[index + 1 :]:
                similarity = _claim_similarity(
                    left.canonical_claim, right.canonical_claim
                )
                if similarity < self.conflict_similarity_threshold:
                    continue
                comparable_pairs += 1
                if _is_negative(left.canonical_claim) != _is_negative(
                    right.canonical_claim
                ):
                    conflicting_pairs += 1
        if comparable_pairs == 0:
            return 0.0
        return conflicting_pairs / comparable_pairs


def _evidence_key(item: EvidenceItem) -> tuple[str, str]:
    return item.source_id, _normalize_support(item.support_span)


def _normalize_support(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _support_overlap(left: str, right: str) -> float:
    left_tokens = _claim_tokens(left)
    right_tokens = _claim_tokens(right)
    smaller = min(len(left_tokens), len(right_tokens))
    if smaller == 0:
        return 0.0
    return len(left_tokens & right_tokens) / smaller


def _is_negative(text: str) -> bool:
    lowered = text.casefold()
    tokens = set(tokenize(lowered))
    return any(marker in lowered for marker in _CJK_NEGATION_MARKERS) or bool(
        tokens & _ENGLISH_NEGATION_MARKERS
    )


def _claim_similarity(left: str, right: str) -> float:
    negation_markers = _CJK_NEGATION_MARKERS | _ENGLISH_NEGATION_MARKERS
    ignored = negation_markers | _CLAIM_STOPWORDS
    left_tokens = _claim_tokens(left) - ignored
    right_tokens = _claim_tokens(right) - ignored
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(left_tokens & right_tokens) / len(union)


def _claim_tokens(text: str) -> set[str]:
    return {
        token
        for token in tokenize(text)
        if re.fullmatch(r"[\u3400-\u9fff]|[a-z0-9_]+", token)
    }
