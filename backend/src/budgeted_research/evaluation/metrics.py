from __future__ import annotations

from collections import Counter
from statistics import fmean, pstdev

from budgeted_research.domain.models import EvidenceMetrics, RunStatus
from budgeted_research.evaluation.models import (
    EvaluationSuite,
    EvaluationSummary,
    PolicyAggregate,
    PolicyRunMetrics,
    TaskEvaluation,
)
from budgeted_research.engine.result import ResearchRunResult


def build_run_metrics(
    result: ResearchRunResult,
    *,
    artifact_directory: str,
    repetition: int = 1,
) -> PolicyRunMetrics:
    summary = result.summary
    metrics = (
        [
            result.state.evidence_metrics.get(item.id, EvidenceMetrics())
            for item in result.state.subquestions
        ]
        if result.state.subquestions
        else list(result.state.evidence_metrics.values())
    )
    report = summary.report
    return PolicyRunMetrics(
        run_id=summary.run_id,
        repetition=repetition,
        policy=summary.policy,
        status=summary.status,
        stop_reason=summary.stop_reason,
        evidence_sufficient=(
            summary.completion_assessment.sufficient
            if summary.policy == "adaptive_budget"
            and summary.completion_assessment is not None
            else None
        ),
        total_tokens=summary.total_tokens,
        total_cost_usd=summary.total_cost_usd,
        search_count=summary.search_count,
        page_fetch_count=summary.page_fetch_count,
        elapsed_seconds=summary.elapsed_seconds,
        evidence_count=len(summary.evidence),
        claim_cluster_count=sum(item.claim_cluster_count for item in metrics),
        mean_coverage=_mean([item.coverage for item in metrics]),
        mean_source_diversity=_mean(
            [item.source_diversity for item in metrics]
        ),
        mean_source_quality=_mean(
            [item.source_quality_score for item in metrics]
        ),
        report_assertion_count=(
            sum(len(section.assertions) for section in report.sections)
            if report is not None
            else 0
        ),
        citation_count=len(report.citation_ids) if report is not None else 0,
        artifact_directory=artifact_directory,
    )


def build_task_evaluation(
    *,
    task_id: str,
    question: str,
    category: str,
    runs: dict[str, list[PolicyRunMetrics]],
) -> TaskEvaluation:
    return TaskEvaluation(
        task_id=task_id,
        question=question,
        category=category,
        runs=runs,
        aggregates={
            policy: _aggregate_runs(policy, policy_runs)
            for policy, policy_runs in runs.items()
        },
    )


def build_evaluation_summary(
    *,
    evaluation_id: str,
    suite: EvaluationSuite,
    task_evaluations: list[TaskEvaluation],
    policies: list[str],
    repetitions_per_task: int = 1,
) -> EvaluationSummary:
    aggregates = {
        policy: _aggregate_policy(policy, task_evaluations) for policy in policies
    }
    return EvaluationSummary(
        evaluation_id=evaluation_id,
        suite_name=suite.name,
        suite_version=suite.version,
        policies=policies,
        repetitions_per_task=repetitions_per_task,
        tasks=task_evaluations,
        aggregates=aggregates,
        caveats=[
            "Coverage and source metrics are operational proxies, not factual accuracy.",
            "No human or LLM judge score is included in this evaluation version.",
            "USD cost is incomplete when provider pricing is not configured.",
            "FAILED attempts are included in failure and total-attempt accounting but "
            "excluded from policy metric means and standard deviations.",
            "Standard deviations describe observed live-run variability and are not "
            "confidence intervals.",
            "Top-level standard deviations combine within-task run variability and "
            "between-task difficulty; use task aggregates to inspect provider variance.",
        ],
    )


def _aggregate_policy(
    policy: str, task_evaluations: list[TaskEvaluation]
) -> PolicyAggregate:
    runs = [
        run
        for task in task_evaluations
        for run in task.runs.get(policy, [])
    ]
    return _aggregate_runs(policy, runs)


def _aggregate_runs(
    policy: str, runs: list[PolicyRunMetrics]
) -> PolicyAggregate:
    evaluated_runs = [
        run
        for run in runs
        if run.status not in {RunStatus.FAILED, RunStatus.CANCELLED}
    ]
    failed_run_count = len(runs) - len(evaluated_runs)
    if not runs:
        return PolicyAggregate(
            policy=policy,
            run_count=0,
            evaluated_run_count=0,
            failed_run_count=0,
            failure_rate=0.0,
            completion_rate=0.0,
            status_counts={},
            total_attempt_tokens=0,
            total_attempt_cost_usd=0.0,
            evidence_sufficient_rate=None,
            mean_tokens=0.0,
            stddev_tokens=0.0,
            mean_cost_usd=0.0,
            stddev_cost_usd=0.0,
            mean_searches=0.0,
            stddev_searches=0.0,
            mean_page_fetches=0.0,
            stddev_page_fetches=0.0,
            mean_elapsed_seconds=0.0,
            stddev_elapsed_seconds=0.0,
            mean_coverage=0.0,
            stddev_coverage=0.0,
            mean_coverage_per_10k_tokens=0.0,
            stddev_coverage_per_10k_tokens=0.0,
            mean_source_diversity=0.0,
            stddev_source_diversity=0.0,
            mean_source_quality=0.0,
            stddev_source_quality=0.0,
            mean_report_assertions=0.0,
            stddev_report_assertions=0.0,
        )
    assessed_sufficiency = [
        run.evidence_sufficient
        for run in evaluated_runs
        if run.evidence_sufficient is not None
    ]
    completed_statuses = {
        RunStatus.COMPLETED,
        RunStatus.COMPLETED_WITH_LIMITATIONS,
    }
    coverage_efficiencies = [
        (
            run.mean_coverage * 10_000 / run.total_tokens
            if run.total_tokens > 0
            else 0.0
        )
        for run in evaluated_runs
    ]
    return PolicyAggregate(
        policy=policy,
        run_count=len(runs),
        evaluated_run_count=len(evaluated_runs),
        failed_run_count=failed_run_count,
        failure_rate=round(failed_run_count / len(runs), 4),
        completion_rate=round(
            sum(run.status in completed_statuses for run in runs) / len(runs),
            4,
        ),
        status_counts=dict(Counter(run.status.value for run in runs)),
        total_attempt_tokens=sum(run.total_tokens for run in runs),
        total_attempt_cost_usd=round(
            sum(run.total_cost_usd for run in runs), 6
        ),
        evidence_sufficient_rate=(
            round(
                sum(value is True for value in assessed_sufficiency)
                / len(assessed_sufficiency),
                4,
            )
            if assessed_sufficiency
            else None
        ),
        mean_tokens=_mean([run.total_tokens for run in evaluated_runs]),
        stddev_tokens=_stddev([run.total_tokens for run in evaluated_runs]),
        mean_cost_usd=_mean([run.total_cost_usd for run in evaluated_runs]),
        stddev_cost_usd=_stddev([run.total_cost_usd for run in evaluated_runs]),
        mean_searches=_mean([run.search_count for run in evaluated_runs]),
        stddev_searches=_stddev([run.search_count for run in evaluated_runs]),
        mean_page_fetches=_mean(
            [run.page_fetch_count for run in evaluated_runs]
        ),
        stddev_page_fetches=_stddev(
            [run.page_fetch_count for run in evaluated_runs]
        ),
        mean_elapsed_seconds=_mean(
            [run.elapsed_seconds for run in evaluated_runs]
        ),
        stddev_elapsed_seconds=_stddev(
            [run.elapsed_seconds for run in evaluated_runs]
        ),
        mean_coverage=_mean([run.mean_coverage for run in evaluated_runs]),
        stddev_coverage=_stddev(
            [run.mean_coverage for run in evaluated_runs]
        ),
        mean_coverage_per_10k_tokens=_mean(coverage_efficiencies),
        stddev_coverage_per_10k_tokens=_stddev(coverage_efficiencies),
        mean_source_diversity=_mean(
            [run.mean_source_diversity for run in evaluated_runs]
        ),
        stddev_source_diversity=_stddev(
            [run.mean_source_diversity for run in evaluated_runs]
        ),
        mean_source_quality=_mean(
            [run.mean_source_quality for run in evaluated_runs]
        ),
        stddev_source_quality=_stddev(
            [run.mean_source_quality for run in evaluated_runs]
        ),
        mean_report_assertions=_mean(
            [run.report_assertion_count for run in evaluated_runs]
        ),
        stddev_report_assertions=_stddev(
            [run.report_assertion_count for run in evaluated_runs]
        ),
    )


def _mean(values: list[int | float]) -> float:
    return round(fmean(values), 4) if values else 0.0


def _stddev(values: list[int | float]) -> float:
    return round(pstdev(values), 4) if len(values) > 1 else 0.0
