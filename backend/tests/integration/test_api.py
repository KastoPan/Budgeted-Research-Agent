from pathlib import Path

from fastapi.testclient import TestClient

from budgeted_research.api.app import create_app
from budgeted_research.domain.events import ActionRecord
from budgeted_research.domain.actions import ActionStatus, ActionType
from budgeted_research.domain.models import ResearchRequest, RunStatus
from budgeted_research.storage.database import Database
from budgeted_research.storage.records import StoredRun
from budgeted_research.storage.repository import RunRepository


class StubRunManager:
    def __init__(self, repository: RunRepository) -> None:
        self.repository = repository
        self.profile: str | None = None

    async def start(
        self,
        request: ResearchRequest,
        policy: str,
        profile: str = "standard",
    ) -> StoredRun:
        self.profile = profile
        return self.repository.create_run(
            "api-run",
            request,
            "adaptive_budget",
            profile,
        )

    async def close(self) -> None:
        pass

    async def cancel(self, run_id: str) -> StoredRun:
        self.repository.mark_cancelled(run_id)
        stored = self.repository.get_run(run_id)
        assert stored is not None
        return stored


def test_api_creates_and_lists_runs_without_provider_calls(tmp_path: Path) -> None:
    database = Database.sqlite_file(tmp_path / "api.db")
    repository = RunRepository(database)
    manager = StubRunManager(repository)
    app = create_app(
        database=database,
        repository=repository,
        manager=manager,  # type: ignore[arg-type]
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/runs",
            json={
                "question": "Compare Python list and tuple",
                "policy": "adaptive",
                "profile": "smoke",
            },
        )
        assert response.status_code == 202
        assert response.json()["run_id"] == "api-run"
        assert response.json()["status"] == "pending"
        assert response.json()["profile"] == "smoke"
        assert manager.profile == "smoke"

        response = client.post("/api/v1/runs/api-run/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

        response = client.post("/api/v1/runs/api-run/cancel")
        assert response.status_code == 409

        response = client.get("/api/v1/runs")
        assert response.status_code == 200
        assert [run["run_id"] for run in response.json()] == ["api-run"]

        response = client.get("/api/v1/runs/api-run/evidence")
        assert response.status_code == 200
        assert response.json() == []

        response = client.post(
            "/api/v1/runs",
            json={
                "question": "Compare Python list and tuple",
                "policy": "adaptive",
                "profile": "unknown",
            },
        )
        assert response.status_code == 422

    database.dispose()


def test_sse_replays_persisted_events_and_terminal_status(tmp_path: Path) -> None:
    database = Database.sqlite_file(tmp_path / "api.db")
    repository = RunRepository(database)
    app = create_app(
        database=database,
        repository=repository,
        manager=StubRunManager(repository),  # type: ignore[arg-type]
        event_poll_seconds=0.01,
    )

    with TestClient(app) as client:
        request = ResearchRequest(question="Compare Python list and tuple")
        repository.create_run("replay-run", request, "fixed_depth")
        repository.append_event(
            "replay-run",
            ActionRecord(
                sequence=1,
                action_id="action-1",
                action_type=ActionType.PLAN,
                policy="fixed_depth",
                reason="test plan",
                status=ActionStatus.COMPLETED,
            ),
        )
        repository.mark_failed("replay-run", "test terminal state")

        response = client.get("/api/v1/runs/replay-run/events/stream")
        assert response.status_code == 200
        assert "id: 1" in response.text
        assert "event: action" in response.text
        assert "event: run" in response.text
        assert '"status": "failed"' in response.text

        response = client.get(
            "/api/v1/runs/replay-run/events/stream",
            headers={"Last-Event-ID": "1"},
        )
        assert "event: action" not in response.text
        assert "event: run" in response.text

    assert repository.get_run("replay-run").status is RunStatus.FAILED  # type: ignore[union-attr]
    database.dispose()
