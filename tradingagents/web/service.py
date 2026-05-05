from __future__ import annotations

from typing import Any

from .database import WebRepository
from .runner import AnalysisRunner
from .schemas import AnalysisCreate, AnalysisRerun, EventPayload


class AnalysisService:
    def __init__(self, repository: WebRepository, runner: AnalysisRunner):
        self.repository = repository
        self.runner = runner

    def create_analysis(self, user_id: int, params: AnalysisCreate, *, run_inline: bool) -> dict[str, Any]:
        task = self.repository.create_task(user_id, params)
        if run_inline:
            self.run_task(task["id"], params)
            task = self.repository.get_task_for_user(task["id"], user_id, include_detail=False) or task
        return task

    def run_task(self, task_id: int, params: AnalysisCreate) -> None:
        self.repository.update_task_status(task_id, "running")
        memory_context = self.repository.build_memory_context_for_task(task_id, max_chars=4000)
        params = params.model_copy(update={"memory_context": memory_context})

        def emit(event: EventPayload) -> None:
            self.repository.append_event(task_id, event)

        try:
            result = self.runner.run(params, emit)
        except Exception as exc:  # pragma: no cover - covered through API by future runner tests
            self.repository.append_event(task_id, EventPayload(agent="System", event_type="task.failed", message=str(exc)))
            self.repository.update_task_status(task_id, "failed", error=str(exc))
            raise
        self.repository.save_report_sections(task_id, result.report_sections)
        self.repository.save_final_decision(task_id, result.final_decision)
        owner_id = self.repository.get_task_owner_id(task_id)
        if owner_id is not None:
            self.repository.extract_agent_memories(owner_id, task_id, params.parameter_payload(), result.report_sections)
        self.repository.update_task_status(task_id, "completed")

    def rerun(self, user_id: int, original_task_id: int, overrides: AnalysisRerun, *, run_inline: bool) -> dict[str, Any] | None:
        original = self.repository.get_task_for_user(original_task_id, user_id, include_detail=False)
        if not original:
            return None
        params = dict(original["parameters"])
        for key, value in overrides.model_dump(exclude_none=True).items():
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            params[key] = value
        return self.create_analysis(user_id, AnalysisCreate(**params), run_inline=run_inline)
