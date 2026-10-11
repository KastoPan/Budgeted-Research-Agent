from __future__ import annotations

from pydantic import Field, model_validator

from budgeted_research.domain.models import DomainModel, ResearchBudget, RunStatus


class EvaluationTask(DomainModel):
    id: str
    question: str
    category: str
    budget: ResearchBudget
    tags: list[str] = Field(default_factory=list)


class EvaluationSuite(DomainModel):
    name: str
    version: str
    description: str = ""
    tasks: list[EvaluationTask] = Field(min_length=1)

    @model_validator(mode="after")
    def task_ids_are_unique(self) -> EvaluationSuite:
        ids = [task.id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("evaluation task IDs must be unique")
        return self


class PolicyRunMetrics(DomainModel):
    run_id: str
    repetition: int = Field(default=1, gt=0)
    policy: str
    status: RunStatus
    stop_reason: str | None = None
    evidence_sufficient: bool | None = None
    total_tokens: int
    total_cost_usd: float
    search_count: int
    page_fetch_count: int
    elapsed_seconds: float
    evidence_count: int
    claim_cluster_count: int
    mean_coverage: float
    mean_source_diversity: float
    mean_source_quality: float
    report_assertion_count: int
    citation_count: int
    artifact_directory: str


class PolicyAggregate(DomainModel):
    policy: str
    run_count: int
    evaluated_run_count: int
    failed_run_count: int
    failure_rate: float
    completion_rate: float
    status_counts: dict[str, int]
    total_attempt_tokens: int
    total_attempt_cost_usd: float
    evidence_sufficient_rate: float | None = None
    mean_tokens: float
    stddev_tokens: float
    mean_cost_usd: float
    stddev_cost_usd: float
    mean_searches: float
    stddev_searches: float
    mean_page_fetches: float
    stddev_page_fetches: float
    mean_elapsed_seconds: float
    stddev_elapsed_seconds: float
    mean_coverage: float
    stddev_coverage: float
    mean_coverage_per_10k_tokens: float
    stddev_coverage_per_10k_tokens: float
    mean_source_diversity: float
    stddev_source_diversity: float
    mean_source_quality: float
    stddev_source_quality: float
    mean_report_assertions: float
    stddev_report_assertions: float


class TaskEvaluation(DomainModel):
    task_id: str
    question: str
    category: str
    runs: dict[str, list[PolicyRunMetrics]]
    aggregates: dict[str, PolicyAggregate]


class EvaluationSummary(DomainModel):
    evaluation_id: str
    suite_name: str
    suite_version: str
    policies: list[str]
    repetitions_per_task: int = Field(gt=0)
    tasks: list[TaskEvaluation]
    aggregates: dict[str, PolicyAggregate]
    caveats: list[str] = Field(default_factory=list)
