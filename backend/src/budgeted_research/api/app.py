from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from budgeted_research.api.schemas import CreateRunRequest
from budgeted_research.application.run_manager import RunManager
from budgeted_research.domain.events import ActionRecord
from budgeted_research.domain.models import EvidenceItem, ResearchReport, RunStatus
from budgeted_research.storage.database import Database
from budgeted_research.storage.records import StoredRun
from budgeted_research.storage.repository import RunRepository


TERMINAL_STATUSES = {
    RunStatus.COMPLETED,
    RunStatus.COMPLETED_WITH_LIMITATIONS,
    RunStatus.BUDGET_EXHAUSTED,
    RunStatus.INSUFFICIENT_EVIDENCE,
    RunStatus.CANCELLED,
    RunStatus.FAILED,
}


def create_app(
    *,
    database: Database | None = None,
    repository: RunRepository | None = None,
    manager: RunManager | None = None,
    database_path: Path | None = None,
    artifact_root: Path | None = None,
    event_poll_seconds: float = 0.5,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    if event_poll_seconds <= 0:
        raise ValueError("event_poll_seconds must be positive")
    owned_database = database is None
    database = database or Database.sqlite_file(
        database_path
        or Path(os.getenv("BRA_DATABASE_PATH", "data/budgeted-research.db"))
    )
    repository = repository or RunRepository(database)
    manager = manager or RunManager(
        repository,
        artifact_root or Path(os.getenv("BRA_RUNS_PATH", "runs")),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(database.create_schema)
        await asyncio.to_thread(repository.recover_interrupted_runs)
        yield
        await manager.close()
        if owned_database:
            await asyncio.to_thread(database.dispose)

    app = FastAPI(
        title="Budgeted Research Agent API",
        version="0.1.0",
        lifespan=lifespan,
    )
    origins = (
        cors_origins
        if cors_origins is not None
        else [
            origin.strip()
            for origin in os.getenv(
                "BRA_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if origin.strip()
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.database = database
    app.state.repository = repository
    app.state.run_manager = manager

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post(
        "/api/v1/runs",
        response_model=StoredRun,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_run(payload: CreateRunRequest) -> StoredRun:
        return await manager.start(
            payload.research_request(),
            payload.policy,
            payload.profile,
        )

    @app.get("/api/v1/runs", response_model=list[StoredRun])
    async def list_runs(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> list[StoredRun]:
        return await asyncio.to_thread(
            repository.list_runs,
            limit=limit,
            offset=offset,
        )

    @app.get("/api/v1/runs/{run_id}", response_model=StoredRun)
    async def get_run(run_id: str) -> StoredRun:
        return await _require_run(repository, run_id)

    @app.post("/api/v1/runs/{run_id}/cancel", response_model=StoredRun)
    async def cancel_run(run_id: str) -> StoredRun:
        stored = await _require_run(repository, run_id)
        if stored.status in TERMINAL_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"run is already terminal: {stored.status.value}",
            )
        try:
            return await manager.cancel(run_id)
        except RuntimeError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error

    @app.get("/api/v1/runs/{run_id}/events", response_model=list[ActionRecord])
    async def get_events(
        run_id: str,
        after: int = Query(default=0, ge=0),
    ) -> list[ActionRecord]:
        await _require_run(repository, run_id)
        return await asyncio.to_thread(repository.list_events, run_id, after=after)

    @app.get("/api/v1/runs/{run_id}/evidence", response_model=list[EvidenceItem])
    async def get_evidence(run_id: str) -> list[EvidenceItem]:
        await _require_run(repository, run_id)
        return await asyncio.to_thread(repository.list_evidence, run_id)

    @app.get("/api/v1/runs/{run_id}/report", response_model=ResearchReport)
    async def get_report(run_id: str) -> ResearchReport:
        await _require_run(repository, run_id)
        report = await asyncio.to_thread(repository.get_report, run_id)
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="report is not available",
            )
        return report

    @app.get("/api/v1/runs/{run_id}/report.md")
    async def get_report_markdown(run_id: str) -> Response:
        await _require_run(repository, run_id)
        report = await asyncio.to_thread(repository.get_report, run_id)
        if report is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="report is not available",
            )
        return Response(report.markdown, media_type="text/markdown")

    @app.get("/api/v1/runs/{run_id}/events/stream")
    async def stream_events(
        request: Request,
        run_id: str,
        after: int = Query(default=0, ge=0),
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        await _require_run(repository, run_id)
        cursor = _event_cursor(after, last_event_id)
        return StreamingResponse(
            _event_stream(
                request,
                repository,
                run_id,
                cursor,
                event_poll_seconds,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return app


async def _require_run(repository: RunRepository, run_id: str) -> StoredRun:
    stored = await asyncio.to_thread(repository.get_run, run_id)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="run not found",
        )
    return stored


def _event_cursor(after: int, last_event_id: str | None) -> int:
    if last_event_id is None:
        return after
    try:
        return max(after, int(last_event_id))
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Last-Event-ID must be an integer",
        ) from error


async def _event_stream(
    request: Request,
    repository: RunRepository,
    run_id: str,
    cursor: int,
    poll_seconds: float,
) -> AsyncIterator[str]:
    stored = await asyncio.to_thread(repository.get_run, run_id)
    if stored is None:
        return
    last_status = stored.status
    yield _sse("run", stored.model_dump(mode="json"))

    idle_polls = 0
    while not await request.is_disconnected():
        events = await asyncio.to_thread(repository.list_events, run_id, after=cursor)
        for event in events:
            cursor = event.sequence
            yield _sse("action", event.model_dump(mode="json"), event.sequence)
        stored = await asyncio.to_thread(repository.get_run, run_id)
        if stored is None:
            return
        if stored.status != last_status:
            yield _sse("run", stored.model_dump(mode="json"))
            last_status = stored.status
        if stored.status in TERMINAL_STATUSES:
            return
        idle_polls += 1
        if idle_polls >= max(1, round(15 / poll_seconds)):
            yield ": keep-alive\n\n"
            idle_polls = 0
        await asyncio.sleep(poll_seconds)


def _sse(event: str, data: dict, event_id: int | None = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    return "\n".join(lines) + "\n\n"


# Uvicorn imports this module directly, unlike the CLI entry point. Load the
# backend-local file here while preserving explicitly exported environment values.
load_dotenv(
    dotenv_path=Path(__file__).resolve().parents[3] / ".env",
    override=False,
)
app = create_app()
