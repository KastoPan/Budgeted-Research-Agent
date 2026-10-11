from pathlib import Path

import pytest

from budgeted_research.application.offline_demo import OfflineDemoService
from budgeted_research.domain.models import RunStatus


@pytest.mark.asyncio
async def test_offline_demo_writes_replayable_run_artifacts(tmp_path: Path) -> None:
    result, artifact_directory, action_count = await OfflineDemoService().run(
        "验证离线研究产物", tmp_path
    )

    assert result.summary.status is RunStatus.COMPLETED
    assert action_count == 14
    assert set(result.state.selected_chunks) == {"sq_01", "sq_02", "sq_03", "sq_04"}
    assert {path.name for path in artifact_directory.iterdir()} == {
        "request.json",
        "events.jsonl",
        "state-final.json",
        "evidence.json",
        "metrics.json",
        "claim-clusters.json",
        "usage.json",
        "report.md",
        "summary.json",
    }
    assert len((artifact_directory / "events.jsonl").read_text().splitlines()) == 14
    report = (artifact_directory / "report.md").read_text()
    assert "[ev_01]" not in report
    assert "https://example.com/offline-source-1" in report
