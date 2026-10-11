from __future__ import annotations

import re

from budgeted_research.domain.models import (
    EvidenceItem,
    ReportAssertion,
    ReportSection,
    ResearchReport,
    SubQuestion,
)


class CitationRenderer:
    """Validates structured assertions and renders the only final prose path."""

    _whitespace_pattern = re.compile(r"\s+")

    def __init__(self, max_assertions_per_section: int = 6) -> None:
        if max_assertions_per_section <= 0:
            raise ValueError("max_assertions_per_section must be positive")
        self.max_assertions_per_section = max_assertions_per_section

    def render(
        self,
        report: ResearchReport,
        evidence: list[EvidenceItem],
        *,
        question: str,
        subquestions: list[SubQuestion],
    ) -> ResearchReport:
        evidence_by_id = {item.id: item for item in evidence}
        accepted_sections: list[ReportSection] = []
        citation_ids: list[str] = []
        rejection_reasons: list[str] = []
        omitted_assertion_count = 0
        lines = [f"# {question.strip()}", ""]
        known_subquestions = {item.id: item for item in subquestions}
        assertions_by_subquestion: dict[str, list[ReportAssertion]] = {
            item.id: [] for item in subquestions
        }

        for section in report.sections:
            if section.subquestion_id not in known_subquestions:
                for assertion_index, _ in enumerate(section.assertions, start=1):
                    rejection_reasons.append(
                        f"unknown subquestion {section.subquestion_id} "
                        f"assertion {assertion_index}"
                    )
                continue
            assertions_by_subquestion[section.subquestion_id].extend(section.assertions)

        for section_index, subquestion in enumerate(subquestions, start=1):
            accepted: list[ReportAssertion] = []
            lines.extend([f"## {subquestion.question.strip()}", ""])
            assertions = assertions_by_subquestion[subquestion.id]
            for assertion_index, assertion in enumerate(assertions, start=1):
                location = f"section {section_index} assertion {assertion_index}"
                known_ids = [
                    evidence_id
                    for evidence_id in assertion.evidence_ids
                    if evidence_id in evidence_by_id
                ]
                unknown_ids = sorted(set(assertion.evidence_ids) - evidence_by_id.keys())
                if unknown_ids:
                    rejection_reasons.append(
                        f"{location}: unknown evidence IDs {unknown_ids}"
                    )
                    continue
                if not self._citations_support_assertion(
                    assertion.text,
                    known_ids,
                    subquestion.id,
                    evidence_by_id,
                ):
                    rejection_reasons.append(
                        f"{location}: cited evidence does not exactly support this "
                        "subquestion assertion"
                    )
                    continue

                if len(accepted) >= self.max_assertions_per_section:
                    omitted_assertion_count += 1
                    continue

                unique_ids = list(dict.fromkeys(known_ids))
                accepted_assertion = ReportAssertion(
                    text=assertion.text.strip(), evidence_ids=unique_ids
                )
                accepted.append(accepted_assertion)
                for evidence_id in unique_ids:
                    if evidence_id not in citation_ids:
                        citation_ids.append(evidence_id)
                citations = " ".join(
                    self._citation_link(evidence_by_id[evidence_id])
                    for evidence_id in unique_ids
                )
                lines.append(f"- {assertion.text.strip()} {citations}")

            if not accepted:
                lines.append("证据不足，当前没有可写入的已验证结论。")
            lines.append("")
            accepted_sections.append(
                ReportSection(
                    subquestion_id=subquestion.id,
                    heading=subquestion.question.strip(),
                    assertions=accepted,
                )
            )

        return ResearchReport(
            title=question.strip(),
            sections=accepted_sections,
            markdown="\n".join(lines).rstrip(),
            citation_ids=citation_ids,
            rejected_assertion_count=len(rejection_reasons),
            omitted_assertion_count=omitted_assertion_count,
            rejection_reasons=rejection_reasons,
        )

    def _citations_support_assertion(
        self,
        text: str,
        evidence_ids: list[str],
        subquestion_id: str,
        evidence_by_id: dict[str, EvidenceItem],
    ) -> bool:
        normalized_text = self._normalize(text)
        return bool(evidence_ids) and all(
            evidence_by_id[evidence_id].subquestion_id == subquestion_id
            and normalized_text == self._normalize(evidence_by_id[evidence_id].claim)
            for evidence_id in evidence_ids
        )

    @classmethod
    def _normalize(cls, value: str) -> str:
        return cls._whitespace_pattern.sub(" ", value).strip()

    @staticmethod
    def _citation_link(item: EvidenceItem) -> str:
        return f"[{item.source_title}]({item.source_url})"
