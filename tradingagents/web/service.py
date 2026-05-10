from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
import queue
import threading
from typing import Any

from .database import WebRepository
from .runner import AnalysisRunner
from .schemas import AnalysisCreate, AnalysisRerun, EventPayload


class AnalysisCancelled(RuntimeError):
    """Raised when a cooperative runner observes that its task was cancelled."""


class AnalysisPaused(RuntimeError):
    """Raised when a cooperative runner observes that its task was paused."""


AnalysisCompletionCallback = Callable[[int, BaseException | None], None]


@dataclass(frozen=True)
class QueuedAnalysis:
    task_id: int
    params: AnalysisCreate
    on_complete: AnalysisCompletionCallback | None = None


class AnalysisService:
    def __init__(self, repository: WebRepository, runner: AnalysisRunner):
        self.repository = repository
        self.runner = runner
        self._queue: queue.Queue[QueuedAnalysis | None] | None = None
        self._workers: list[threading.Thread] = []
        self._queue_lock = threading.Lock()

    def create_analysis(self, user_id: int, params: AnalysisCreate, *, run_inline: bool) -> dict[str, Any]:
        task = self.repository.create_task(user_id, params)
        if run_inline:
            self.run_task(task["id"], params)
            task = self.repository.get_task_for_user(task["id"], user_id, include_detail=False) or task
        return task

    def start_queue(self, *, max_workers: int = 1) -> None:
        worker_count = max(1, max_workers)
        with self._queue_lock:
            if self._queue is not None:
                return
            self._queue = queue.Queue()
            self._workers = [
                threading.Thread(
                    target=self._queue_worker,
                    name=f"tradingagents-analysis-worker-{index + 1}",
                    daemon=True,
                )
                for index in range(worker_count)
            ]
            for worker in self._workers:
                worker.start()

    def stop_queue(self, *, timeout: float = 5.0) -> None:
        with self._queue_lock:
            task_queue = self._queue
            workers = list(self._workers)
            if task_queue is None:
                return
            for _ in workers:
                task_queue.put(None)
            self._queue = None
            self._workers = []
        for worker in workers:
            worker.join(timeout=timeout)

    def enqueue_task(self, task_id: int, params: AnalysisCreate, on_complete: AnalysisCompletionCallback | None = None) -> None:
        task_queue = self._queue
        if task_queue is None:
            raise RuntimeError("analysis queue has not been started")
        task_queue.put(QueuedAnalysis(task_id=task_id, params=params, on_complete=on_complete))

    def _queue_worker(self) -> None:
        task_queue = self._queue
        if task_queue is None:
            return
        while True:
            item = task_queue.get()
            try:
                if item is None:
                    return
                exc: BaseException | None = None
                try:
                    if self.repository.get_task_status(item.task_id) == "queued":
                        self.run_task(item.task_id, item.params)
                except BaseException as error:  # pragma: no cover - run_task persists failure details
                    exc = error
                if item.on_complete:
                    item.on_complete(item.task_id, exc)
            finally:
                task_queue.task_done()

    def run_task(self, task_id: int, params: AnalysisCreate) -> None:
        self.repository.update_task_status(task_id, "running")
        memory_context = self.repository.build_memory_context_for_task(task_id, max_chars=4000)
        params = params.model_copy(update={"memory_context": memory_context})

        def emit(event: EventPayload) -> None:
            status = self.repository.get_task_status(task_id)
            if status == "cancelled":
                raise AnalysisCancelled("analysis task was cancelled")
            if status == "paused":
                raise AnalysisPaused("analysis task was paused")
            self.repository.append_event(task_id, event)

        try:
            result = self.runner.run(params, emit)
        except (AnalysisCancelled, AnalysisPaused):
            return
        except Exception as exc:  # pragma: no cover - covered through API by future runner tests
            if self.repository.get_task_status(task_id) == "cancelled":
                return
            self.repository.append_event(task_id, EventPayload(agent="System", event_type="task.failed", message=str(exc)))
            self.repository.update_task_status(task_id, "failed", error=str(exc))
            raise
        if self.repository.get_task_status(task_id) in {"cancelled", "paused"}:
            return
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
