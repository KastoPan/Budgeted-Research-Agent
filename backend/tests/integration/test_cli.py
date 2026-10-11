import json
from pathlib import Path

from typer.testing import CliRunner

from budgeted_research.cli.app import app

runner = CliRunner()


def test_offline_demo_is_parsed_as_a_subcommand(tmp_path: Path) -> None:
    output_root = tmp_path / "runs"

    result = runner.invoke(app, ["offline-demo", "--output", str(output_root)])

    assert result.exit_code == 0, result.output
    assert "status: completed" in result.output
    run_directories = list(output_root.iterdir())
    assert len(run_directories) == 1
    request = json.loads((run_directories[0] / "request.json").read_text())
    assert request["question"] == "比较研究 Agent 的架构、成本、证据可靠性与工程适用性"


def test_live_research_fails_before_network_when_credentials_are_missing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_MODEL", raising=False)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    result = runner.invoke(app, ["research", "test question"])

    assert result.exit_code == 2
    assert "MOONSHOT_API_KEY and MOONSHOT_MODEL are required" in result.output
    assert not (tmp_path / "runs").exists()
