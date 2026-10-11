from __future__ import annotations

import asyncio

from budgeted_research.domain.events import ActionRecord
from budgeted_research.storage.repository import RunRepository


class PersistentEventSink:
    def __init__(self, run_id: str, repository: RunRepository) -> None:
        self.run_id = run_id
        self.repository = repository

    async def record(self, event: ActionRecord) -> None:
        await asyncio.to_thread(self.repository.append_event, self.run_id, event)
