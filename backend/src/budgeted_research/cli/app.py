from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path

import typer
from dotenv import load_dotenv

from budgeted_research.application.extraction_check import ExtractionCheckService
from budgeted_research.application.evaluation import LiveEvaluationService
from budgeted_research.application.live_research import LiveResearchService
from budgeted_research.application.offline_demo import OfflineDemoService
from budgeted_research.application.policy_factory import build_research_policy
from budgeted_research.application.provider_check import ProviderCheckService
from budgeted_research.config import ProviderSettings
from budgeted_research.domain.errors import ResearchError
from budgeted_research.domain.models import ResearchBudget, ResearchRequest, RunStatus

app = typer.Typer(
    name="bra",
    help="Run and inspect Budgeted Research Agent workflows.",
    no_args_is_help=True,
)
eval_app = typer.Typer(help="Run reproducible Fixed/Adaptive evaluations.")
app.add_typer(eval_app, name="eval")


@app.callback()
def main() -> None:
    """Budgeted Research Agent command group."""


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="API bind address."),
    port: int = typer.Option(8000, "--port", min=1, max=65535),
    reload: bool = typer.Option(False, "--reload", help="Reload on code changes."),
) -> None:
    """Start the FastAPI service and persistent background run manager."""
    import uvicorn

    load_dotenv(dotenv_path=Path(".env"))
    uvicorn.run(
        "budgeted_research.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


@eval_app.command("run")
def evaluation_run(
    suite: Path = typer.Option(
        Path("evals/dev-suite.json"),
        "--suite",
        help="Versioned JSON evaluation suite.",
    ),
    output: Path = typer.Option(
        Path("evaluations"),
        "--output",
        "-o",
        help="Directory used for evaluation artifacts.",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        min=1,
        help="Run only the first N tasks for a low-cost check.",
    ),
    repetitions: int = typer.Option(
        1,
        "--repetitions",
        "-r",
        min=1,
        help="Repeat every task-policy pair N times to measure live-run variance.",
    ),
) -> None:
    """Run paired live Fixed and Adaptive experiments sequentially."""
    load_dotenv(dotenv_path=Path(".env"))
    try:
        settings = ProviderSettings.from_environment()
        settings.require_moonshot()
        settings.require_tavily_key()
        service = LiveEvaluationService(settings)
        evaluation_suite = service.load_suite(suite)
        summary, evaluation_directory = asyncio.run(
            service.run(
                evaluation_suite,
                output,
                limit=limit,
                repetitions=repetitions,
            )
        )
    except (OSError, ValueError) as error:
        typer.echo(f"evaluation configuration error: {error}", err=True)
        raise typer.Exit(code=2) from error

    typer.echo(f"evaluation_id: {summary.evaluation_id}")
    typer.echo(f"suite: {summary.suite_name}@{summary.suite_version}")
    typer.echo(f"tasks: {len(summary.tasks)}")
    typer.echo(f"repetitions_per_task: {summary.repetitions_per_task}")
    typer.echo(f"artifacts: {evaluation_directory.resolve()}")
    for policy, aggregate in summary.aggregates.items():
        typer.echo(
            f"{policy}: evaluated_runs={aggregate.evaluated_run_count}/"
            f"{aggregate.run_count}, failure_rate={aggregate.failure_rate:.1%}, "
            f"completion_rate={aggregate.completion_rate:.1%}"
        )
        typer.echo(
            f"  resources: tokens={aggregate.mean_tokens:.1f}±"
            f"{aggregate.stddev_tokens:.1f}, "
            f"total_attempt_tokens={aggregate.total_attempt_tokens}, "
            f"cost_usd={aggregate.mean_cost_usd:.6f}, "
            f"searches={aggregate.mean_searches:.2f}, "
            f"page_fetches={aggregate.mean_page_fetches:.2f}, "
            f"elapsed_seconds={aggregate.mean_elapsed_seconds:.1f}"
        )
        typer.echo(
            f"  evidence: coverage={aggregate.mean_coverage:.3f}"
            f"±{aggregate.stddev_coverage:.3f}, "
            f"source_diversity={aggregate.mean_source_diversity:.3f}"
            f"±{aggregate.stddev_source_diversity:.3f}, "
            f"source_quality={aggregate.mean_source_quality:.3f}, "
            f"coverage_per_10k_tokens="
            f"{aggregate.mean_coverage_per_10k_tokens:.3f}"
        )
    if (
        settings.moonshot_input_cost_per_million_usd is None
        or settings.moonshot_output_cost_per_million_usd is None
    ):
        typer.echo(
            "warning: Moonshot USD pricing is not configured; evaluation cost is "
            "incomplete.",
            err=True,
        )


@app.command("offline-demo")
def offline_demo(
    question: str = typer.Argument(
        "比较研究 Agent 的架构、成本、证据可靠性与工程适用性",
        help="Research question used in the deterministic offline run.",
    ),
    output: Path = typer.Option(
        Path("runs"), "--output", "-o", help="Directory used for run artifacts."
    ),
) -> None:
    """Execute a deterministic end-to-end run without network access."""
    result, artifact_directory, action_count = asyncio.run(
        OfflineDemoService().run(question, output)
    )
    summary = result.summary
    typer.echo(f"run_id: {summary.run_id}")
    typer.echo(f"policy: {summary.policy}")
    typer.echo(f"status: {summary.status.value}")
    typer.echo(f"actions: {action_count}")
    typer.echo(f"tokens: {summary.total_tokens}")
    typer.echo(f"searches: {summary.search_count}")
    typer.echo(f"page_fetches: {summary.page_fetch_count}")
    typer.echo(f"artifacts: {artifact_directory.resolve()}")
    if summary.status is not RunStatus.COMPLETED:
        raise typer.Exit(code=1)


@app.command("providers-check")
def providers_check() -> None:
    """Make one minimal request to Kimi and Tavily to verify live configuration."""
    load_dotenv(dotenv_path=Path(".env"))
    try:
        settings = ProviderSettings.from_environment()
        result = asyncio.run(ProviderCheckService(settings).check())
    except ValueError as error:
        typer.echo(f"configuration error: {error}", err=True)
        raise typer.Exit(code=2) from error
    except Exception as error:
        status_code = getattr(error, "status_code", None)
        status_suffix = f" (HTTP {status_code})" if status_code else ""
        detail = _safe_provider_error_detail(error)
        detail_suffix = f": {detail}" if detail else ""
        typer.echo(
            f"provider check failed: {type(error).__name__}{status_suffix}"
            f"{detail_suffix}",
            err=True,
        )
        raise typer.Exit(code=1) from error

    typer.echo(f"moonshot_model: {result.model}")
    typer.echo(f"moonshot_json_mode: {str(result.llm_json_mode).lower()}")
    typer.echo(f"moonshot_tokens: {result.llm_tokens}")
    typer.echo(f"tavily_results: {result.tavily_result_count}")
    typer.echo(f"tavily_request_id: {result.tavily_request_id or 'unavailable'}")
    typer.echo(f"tavily_credits: {result.tavily_credits or 'unavailable'}")
    if not result.llm_json_mode or result.tavily_result_count == 0:
        raise typer.Exit(code=1)


@app.command("research")
def research(
    question: str = typer.Argument(help="Technical research question."),
    output: Path = typer.Option(
        Path("runs"), "--output", "-o", help="Directory used for run artifacts."
    ),
    max_tokens: int = typer.Option(50_000, min=1, help="Hard token budget."),
    max_searches: int = typer.Option(4, min=1, help="Hard search-call budget."),
    max_page_fetches: int = typer.Option(20, min=1, help="Hard page-fetch budget."),
    max_seconds: float = typer.Option(300.0, min=1.0, help="Hard wall-time budget."),
    smoke: bool = typer.Option(
        False,
        "--smoke",
        help="Run a minimal one-question live pipeline without changing baseline defaults.",
    ),
    policy_name: str = typer.Option(
        "fixed",
        "--policy",
        help="Research policy: fixed or adaptive.",
    ),
) -> None:
    """Run research with real Kimi, Tavily, and web providers."""
    load_dotenv(dotenv_path=Path(".env"))
    try:
        settings = ProviderSettings.from_environment()
        request = ResearchRequest(
            question=question,
            budget=ResearchBudget(
                max_tokens=max_tokens,
                max_searches=max_searches,
                max_page_fetches=max_page_fetches,
                max_elapsed_seconds=max_seconds,
            ),
        )
        selected_policy = build_research_policy(
            policy_name,
            "smoke" if smoke else "standard",
        )
        result, artifact_directory, action_count = asyncio.run(
            LiveResearchService(settings, policy=selected_policy).run(request, output)
        )
    except ValueError as error:
        typer.echo(f"configuration error: {error}", err=True)
        raise typer.Exit(code=2) from error

    summary = result.summary
    typer.echo(f"run_id: {summary.run_id}")
    typer.echo(f"policy: {summary.policy}")
    typer.echo(f"status: {summary.status.value}")
    typer.echo(f"actions: {action_count}")
    typer.echo(f"tokens: {summary.total_tokens}")
    typer.echo(f"cost_usd: {summary.total_cost_usd:.6f}")
    typer.echo(f"searches: {summary.search_count}")
    typer.echo(f"page_fetches: {summary.page_fetch_count}")
    typer.echo(f"artifacts: {artifact_directory.resolve()}")
    if (
        settings.moonshot_input_cost_per_million_usd is None
        or settings.moonshot_output_cost_per_million_usd is None
    ):
        typer.echo(
            "warning: Moonshot USD pricing is not configured; cost_usd is incomplete.",
            err=True,
        )
    if summary.status is RunStatus.COMPLETED_WITH_LIMITATIONS:
        typer.echo(f"warning: {summary.stop_reason}", err=True)
        if summary.completion_assessment is not None:
            for condition in summary.completion_assessment.unmet_conditions:
                typer.echo(f"  - {condition}", err=True)
    elif summary.status is not RunStatus.COMPLETED:
        typer.echo(f"stop_reason: {summary.stop_reason}", err=True)
        raise typer.Exit(code=1)


@app.command("extraction-check")
def extraction_check(
    run_directory: Path = typer.Argument(
        help="Existing run directory containing state-final.json."
    ),
    subquestion: str = typer.Option(
        "sq_01", "--subquestion", "-s", help="Subquestion ID to extract."
    ),
) -> None:
    """Retry one Kimi evidence extraction using an existing run's fetched pages."""
    load_dotenv(dotenv_path=Path(".env"))
    try:
        settings = ProviderSettings.from_environment()
        result, output_path = asyncio.run(
            ExtractionCheckService(settings).check(run_directory, subquestion)
        )
    except ValueError as error:
        typer.echo(f"configuration or input error: {error}", err=True)
        raise typer.Exit(code=2) from error
    except ResearchError as error:
        typer.echo(
            f"extraction check failed: {type(error).__name__}: {error}",
            err=True,
        )
        raise typer.Exit(code=1) from error
    except Exception as error:
        status_code = getattr(error, "status_code", None)
        status_suffix = f" (HTTP {status_code})" if status_code else ""
        typer.echo(
            f"extraction check failed: {type(error).__name__}{status_suffix}",
            err=True,
        )
        raise typer.Exit(code=1) from error

    typer.echo(f"run_id: {result.run_id}")
    typer.echo(f"subquestion: {result.subquestion_id}")
    typer.echo(f"selected_chunks: {len(result.selected_chunks)}")
    typer.echo(f"evidence: {len(result.evidence)}")
    typer.echo(f"tokens: {result.usage.total_tokens}")
    typer.echo(f"artifact: {output_path.resolve()}")


def _safe_provider_error_detail(error: Exception) -> str | None:
    body = getattr(error, "body", None)
    if not isinstance(body, Mapping):
        return None
    nested = body.get("error")
    details = nested if isinstance(nested, Mapping) else body
    allowed = ("message", "code", "type", "param")
    parts = [f"{key}={details[key]}" for key in allowed if details.get(key) is not None]
    return ", ".join(parts) or None


if __name__ == "__main__":
    app()
