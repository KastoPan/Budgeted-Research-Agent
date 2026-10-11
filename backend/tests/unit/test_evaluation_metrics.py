from budgeted_research.domain.models import (
    CompletionAssessment,
    EvidenceMetrics,
    ReportAssertion,
    ReportSection,
    ResearchReport,
    ResearchRequest,
    RunStatus,
    RunSummary,
)
from budgeted_research.domain.state import ResearchState
from budgeted_research.engine.result import ResearchRunResult
from budgeted_research.evaluation.metrics import (
    build_evaluation_summary,
    build_run_metrics,
    build_task_evaluation,
)
from budgeted_research.evaluation.models import (
    EvaluationSuite,
    EvaluationTask,
)


def _adaptive_result(run_id: str, tokens: int, coverage: float) -> ResearchRunResult:
    report = ResearchReport(
        title="Comparison",
        sections=[
            ReportSection(
                subquestion_id="sq_01",
                heading="Trade-offs",
                assertions=[
                    ReportAssertion(text="Verified claim", evidence_ids=["ev_01"])
                ],
            )
        ],
        markdown="# Comparison",
        citation_ids=["ev_01"],
    )
    assessment = CompletionAssessment(
        sufficient=True,
        status=RunStatus.COMPLETED,
        reason="targets reached",
    )
    state = ResearchState(
        run_id=run_id,
        request=ResearchRequest(question="Compare two technical approaches"),
        status=RunStatus.COMPLETED,
        report=report,
        evidence_metrics={
            "sq_01": EvidenceMetrics(
                evidence_count=2,
                claim_cluster_count=2,
                source_count=2,
                coverage=coverage,
                source_diversity=1.0,
                source_quality_score=0.8,
            )
        },
        completion_assessment=assessment,
    )
    summary = RunSummary(
        run_id=run_id,
        policy="adaptive_budget",
        status=RunStatus.COMPLETED,
        report=report,
        total_tokens=tokens,
        search_count=2,
        page_fetch_count=3,
        elapsed_seconds=12.5,
        completion_assessment=assessment,
    )
    return ResearchRunResult(state=state, summary=summary)


def test_build_run_metrics_uses_structured_run_state() -> None:
    metrics = build_run_metrics(
        _adaptive_result("run_01", 1_500, 0.8),
        artifact_directory="/tmp/run_01",
    )

    assert metrics.policy == "adaptive_budget"
    assert metrics.evidence_sufficient is True
    assert metrics.total_tokens == 1_500
    assert metrics.claim_cluster_count == 2
    assert metrics.mean_coverage == 0.8
    assert metrics.report_assertion_count == 1
    assert metrics.citation_count == 1


def test_evaluation_summary_aggregates_policy_runs_without_quality_claims() -> None:
    suite = EvaluationSuite(
        name="dev",
        version="0.1.0",
        tasks=[
            EvaluationTask(
                id="task_01",
                question="Compare two technical approaches",
                category="comparison",
                budget=ResearchRequest(
                    question="Compare two technical approaches"
                ).budget,
            )
        ],
    )
    run = build_run_metrics(
        _adaptive_result("run_01", 1_500, 0.8),
        artifact_directory="/tmp/run_01",
    )
    tasks = [
        build_task_evaluation(
            task_id="task_01",
            question="Compare two technical approaches",
            category="comparison",
            runs={"adaptive_budget": [run]},
        )
    ]

    summary = build_evaluation_summary(
        evaluation_id="eval_01",
        suite=suite,
        task_evaluations=tasks,
        policies=["adaptive_budget"],
    )

    aggregate = summary.aggregates["adaptive_budget"]
    assert aggregate.run_count == 1
    assert aggregate.evidence_sufficient_rate == 1.0
    assert aggregate.completion_rate == 1.0
    assert aggregate.mean_tokens == 1_500
    assert aggregate.stddev_tokens == 0.0
    assert aggregate.mean_coverage == 0.8
    assert aggregate.mean_coverage_per_10k_tokens == 5.3333
    assert any("not factual accuracy" in caveat for caveat in summary.caveats)


def test_evaluation_summary_reports_variability_across_repetitions() -> None:
    suite = EvaluationSuite(
        name="dev",
        version="0.1.0",
        tasks=[
            EvaluationTask(
                id="task_01",
                question="Compare two technical approaches",
                category="comparison",
                budget=ResearchRequest(
                    question="Compare two technical approaches"
                ).budget,
            )
        ],
    )
    runs = [
        build_run_metrics(
            _adaptive_result("run_01", 1_500, 0.8),
            artifact_directory="/tmp/run_01",
            repetition=1,
        ),
        build_run_metrics(
            _adaptive_result("run_02", 2_500, 1.0),
            artifact_directory="/tmp/run_02",
            repetition=2,
        ),
    ]
    task = build_task_evaluation(
        task_id="task_01",
        question="Compare two technical approaches",
        category="comparison",
        runs={"adaptive_budget": runs},
    )

    summary = build_evaluation_summary(
        evaluation_id="eval_repeated",
        suite=suite,
        task_evaluations=[task],
        policies=["adaptive_budget"],
        repetitions_per_task=2,
    )

    task_aggregate = summary.tasks[0].aggregates["adaptive_budget"]
    aggregate = summary.aggregates["adaptive_budget"]
    assert summary.repetitions_per_task == 2
    assert [run.repetition for run in summary.tasks[0].runs["adaptive_budget"]] == [
        1,
        2,
    ]
    assert task_aggregate.mean_tokens == 2_000
    assert task_aggregate.stddev_tokens == 500
    assert aggregate.run_count == 2
    assert aggregate.mean_coverage == 0.9
    assert aggregate.stddev_coverage == 0.1


def test_failed_attempts_are_reported_but_excluded_from_policy_means() -> None:
    successful = build_run_metrics(
        _adaptive_result("run_success", 1_500, 0.8),
        artifact_directory="/tmp/run_success",
        repetition=1,
    )
    failed = successful.model_copy(
        update={
            "run_id": "run_failed",
            "repetition": 2,
            "status": RunStatus.FAILED,
            "stop_reason": "ConnectError: transient failure",
            "evidence_sufficient": None,
            "total_tokens": 605,
            "mean_coverage": 0.0,
            "mean_source_diversity": 0.0,
            "mean_source_quality": 0.0,
            "report_assertion_count": 0,
        }
    )
    task = build_task_evaluation(
        task_id="task_01",
        question="Compare two technical approaches",
        category="comparison",
        runs={"adaptive_budget": [successful, failed]},
    )

    aggregate = task.aggregates["adaptive_budget"]

    assert aggregate.run_count == 2
    assert aggregate.evaluated_run_count == 1
    assert aggregate.failed_run_count == 1
    assert aggregate.failure_rate == 0.5
    assert aggregate.completion_rate == 0.5
    assert aggregate.total_attempt_tokens == 2_105
    assert aggregate.mean_tokens == 1_500
    assert aggregate.mean_coverage == 0.8
    assert task.runs["adaptive_budget"][1].stop_reason.startswith("ConnectError")
