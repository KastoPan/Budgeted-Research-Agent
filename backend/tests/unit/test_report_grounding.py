from budgeted_research.domain.models import (
    EvidenceItem,
    ReportAssertion,
    ReportSection,
    ResearchReport,
    SubQuestion,
)
from budgeted_research.reporting.citations import CitationRenderer


def _evidence(evidence_id: str, claim: str) -> EvidenceItem:
    return EvidenceItem(
        id=evidence_id,
        subquestion_id="sq_01",
        claim=claim,
        support_span="A verbatim source passage.",
        source_id=f"src_{evidence_id}",
        source_url=f"https://example.com/{evidence_id}",
        source_title=f"Source {evidence_id}",
    )


def _subquestions() -> list[SubQuestion]:
    return [
        SubQuestion(
            id="sq_01",
            question="Main difference",
            search_query="list tuple difference",
            rationale="Compare semantics",
        )
    ]


def test_renderer_keeps_only_assertions_that_copy_a_cited_claim() -> None:
    evidence = [_evidence("ev_01", "List is mutable; tuple is immutable.")]
    draft = ResearchReport(
        title="Injected title fact",
        sections=[
            ReportSection(
                subquestion_id="sq_01",
                heading="Injected heading fact",
                assertions=[
                    ReportAssertion(
                        text="List is mutable; tuple is immutable.",
                        evidence_ids=["ev_01"],
                    ),
                    ReportAssertion(
                        text="Tuple always uses less memory.", evidence_ids=["ev_01"]
                    ),
                ],
            )
        ],
    )

    rendered = CitationRenderer().render(
        draft, evidence, question="List and tuple", subquestions=_subquestions()
    )

    assert "List is mutable; tuple is immutable." in rendered.markdown
    assert "Tuple always uses less memory." not in rendered.markdown
    assert "Injected title fact" not in rendered.markdown
    assert "Injected heading fact" not in rendered.markdown
    assert rendered.markdown.startswith("# List and tuple\n\n## Main difference")
    assert "[Source ev_01](https://example.com/ev_01)" in rendered.markdown
    assert rendered.citation_ids == ["ev_01"]
    assert rendered.rejected_assertion_count == 1
    assert "does not exactly support" in rendered.rejection_reasons[0]


def test_renderer_rejects_unknown_evidence_without_failing_the_report() -> None:
    draft = ResearchReport(
        title="Report",
        sections=[
            ReportSection(
                subquestion_id="sq_01",
                heading="Section",
                assertions=[
                    ReportAssertion(text="Unsupported.", evidence_ids=["ev_missing"])
                ],
            )
        ],
    )

    rendered = CitationRenderer().render(
        draft, [], question="Report", subquestions=_subquestions()
    )

    assert "Unsupported." not in rendered.markdown
    assert "证据不足" in rendered.markdown
    assert rendered.citation_ids == []
    assert rendered.rejected_assertion_count == 1
    assert "unknown evidence IDs" in rendered.rejection_reasons[0]


def test_renderer_caps_valid_assertions_without_marking_them_rejected() -> None:
    evidence = [
        _evidence(f"ev_{index:02d}", f"Supported claim {index}.")
        for index in range(1, 5)
    ]
    draft = ResearchReport(
        sections=[
            ReportSection(
                subquestion_id="sq_01",
                heading="Ignored heading",
                assertions=[
                    ReportAssertion(text=item.claim, evidence_ids=[item.id])
                    for item in evidence
                ],
            )
        ]
    )

    rendered = CitationRenderer(max_assertions_per_section=2).render(
        draft, evidence, question="Report", subquestions=_subquestions()
    )

    assert len(rendered.sections[0].assertions) == 2
    assert "Supported claim 1." in rendered.markdown
    assert "Supported claim 3." not in rendered.markdown
    assert rendered.omitted_assertion_count == 2
    assert rendered.rejected_assertion_count == 0
