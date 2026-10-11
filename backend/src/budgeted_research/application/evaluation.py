from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from budgeted_research.application.live_research import LiveResearchService
from budgeted_research.config import ProviderSettings
from budgeted_research.domain.models import ResearchRequest
from budgeted_research.evaluation.metrics import (
    build_evaluation_summary,
    build_run_metrics,
    build_task_evaluation,
)
from budgeted_research.evaluation.models import (
    EvaluationSuite,
    EvaluationSummary,
)
from budgeted_research.policies.adaptive_budget import AdaptiveBudgetPolicy
from budgeted_research.policies.fixed_depth import FixedDepthPolicy


class LiveEvaluationService:
    """Runs a versioned task suite against comparable live policies."""

    _policy_factories = {
        "fixed_depth": FixedDepthPolicy,
        "adaptive_budget": AdaptiveBudgetPolicy,
    }

    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings

    @staticmethod
    def load_suite(path: Path) -> EvaluationSuite:
        return EvaluationSuite.model_validate_json(path.read_text(encoding="utf-8"))

    async def run(
        self,
        suite: EvaluationSuite,
        output_root: Path,
        *,
        policies: list[str] | None = None,
        limit: int | None = None,
        repetitions: int = 1,
    ) -> tuple[EvaluationSummary, Path]:
        selected_policies = policies or ["fixed_depth", "adaptive_budget"]
        unknown = set(selected_policies) - self._policy_factories.keys()
        if unknown:
            raise ValueError(f"unknown evaluation policies: {sorted(unknown)}")
        if limit is not None and limit <= 0:
            raise ValueError("evaluation limit must be positive")
        if repetitions <= 0:
            raise ValueError("evaluation repetitions must be positive")

        evaluation_id = str(uuid4())
        evaluation_directory = output_root / evaluation_id
        evaluation_directory.mkdir(parents=True, exist_ok=False)
        run_output_root = evaluation_directory / "runs"
        task_evaluations = []

        tasks = suite.tasks[:limit] if limit is not None else suite.tasks
        for task_index, task in enumerate(tasks):
            runs = {policy_name: [] for policy_name in selected_policies}
            request = ResearchRequest(question=task.question, budget=task.budget)
            for repetition_index in range(repetitions):
                order_index = task_index * repetitions + repetition_index
                policy_order = (
                    selected_policies
                    if order_index % 2 == 0
                    else list(reversed(selected_policies))
                )
                for policy_name in policy_order:
                    policy = self._policy_factories[policy_name]()
                    result, artifact_directory, _ = await LiveResearchService(
                        self.settings, policy=policy
                    ).run(request, run_output_root)
                    runs[policy_name].append(
                        build_run_metrics(
                            result,
                            repetition=repetition_index + 1,
                            artifact_directory=str(artifact_directory.resolve()),
                        )
                    )
            task_evaluations.append(
                build_task_evaluation(
                    task_id=task.id,
                    question=task.question,
                    category=task.category,
                    runs=runs,
                )
            )

        summary = build_evaluation_summary(
            evaluation_id=evaluation_id,
            suite=suite,
            task_evaluations=task_evaluations,
            policies=selected_policies,
            repetitions_per_task=repetitions,
        )
        (evaluation_directory / "suite.json").write_text(
            suite.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        (evaluation_directory / "summary.json").write_text(
            summary.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        return summary, evaluation_directory
