from __future__ import annotations

import json
import time
from collections.abc import Iterator
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlite3 import IntegrityError

from .database import WebRepository
from .intervention import InterventionService
from .runner import DemoAnalysisRunner, TradingAgentsGraphRunner
from .schemas import (
    AnalysisCreate,
    AnalysisRerun,
    InterventionCreate,
    InterventionMessageCreate,
    LoginRequest,
    RunDueRequest,
    ScheduledAnalysisCreate,
    ScheduledAnalysisUpdate,
    MemoryUpdate,
    TokenResponse,
    UserCreate,
)
from .scheduler import SchedulerService, format_iso_datetime
from .service import AnalysisService
from .settings import WebSettings

security = HTTPBearer(auto_error=False)


def create_app(settings: WebSettings | None = None, *, run_tasks_inline: bool = False) -> FastAPI:
    settings = settings or WebSettings()
    settings.validate_for_startup()
    repository = WebRepository(settings.database_path)
    if settings.bootstrap_user_email and settings.bootstrap_user_password and not repository.get_user_by_email(settings.bootstrap_user_email):
        user = repository.create_user(settings.bootstrap_user_email, settings.bootstrap_user_password)
        repository.append_audit_log("auth.user.provisioned", user_id=user["id"], resource_type="user", resource_id=user["id"])
    runner = DemoAnalysisRunner() if settings.runner_mode == "demo" else TradingAgentsGraphRunner()
    service = AnalysisService(repository, runner)
    scheduler_service = SchedulerService(service)
    intervention_service = InterventionService(repository)
    app = FastAPI(title="TradingAgents Web", version="0.1.0")
    app.state.settings = settings
    app.state.repository = repository
    app.state.service = service
    app.state.scheduler_service = scheduler_service
    app.state.intervention_service = intervention_service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    rate_state: dict[tuple[str, str], list[float]] = {}

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    def request_ip(request: Request | None) -> str | None:
        if request is None or request.client is None:
            return None
        return request.client.host

    def audit(
        event_type: str,
        *,
        user_id: int | None = None,
        resource_type: str | None = None,
        resource_id: int | str | None = None,
        metadata: dict | None = None,
        request: Request | None = None,
    ) -> None:
        repository.append_audit_log(
            event_type,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
            ip_address=request_ip(request),
        )

    def rate_identity(request: Request, user: dict | None = None) -> str:
        if user:
            return f"user:{user['id']}"
        return f"ip:{request_ip(request) or 'unknown'}"

    def enforce_rate_limit(scope: str, request: Request, limit: int, user: dict | None = None) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        key = (scope, rate_identity(request, user))
        window_start = now - settings.rate_limit_window_seconds
        hits = [hit for hit in rate_state.get(key, []) if hit > window_start]
        if len(hits) >= limit:
            audit("rate_limit.exceeded", user_id=user["id"] if user else None, resource_type=scope, request=request)
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        hits.append(now)
        rate_state[key] = hits

    def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
        user = repository.get_user_for_token(credentials.credentials)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token")
        return user

    def current_token(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> str:
        if credentials is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
        return credentials.credentials

    @app.get("/health")
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "bind_host": settings.host}

    @app.post("/api/auth/register", status_code=201)
    def register(payload: UserCreate, request: Request) -> dict:
        enforce_rate_limit("auth", request, settings.auth_rate_limit)
        if not settings.allow_registration:
            audit("auth.registration.rejected", metadata={"email": payload.email}, request=request)
            raise HTTPException(status_code=403, detail="registration disabled")
        try:
            user = repository.create_user(payload.email, payload.password)
            audit("auth.register", user_id=user["id"], resource_type="user", resource_id=user["id"], request=request)
            return user
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="user already exists") from exc

    @app.post("/api/auth/login", response_model=TokenResponse)
    def login(payload: LoginRequest, request: Request) -> dict:
        enforce_rate_limit("auth", request, settings.auth_rate_limit)
        user = repository.authenticate(payload.email, payload.password)
        if not user:
            audit("auth.login.failure", metadata={"email": payload.email}, request=request)
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = repository.create_session(user["id"])
        audit("auth.login.success", user_id=user["id"], resource_type="user", resource_id=user["id"], request=request)
        return {"access_token": token, "token_type": "bearer", "user": user}

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, token: str = Depends(current_token), user: dict = Depends(current_user)) -> Response:
        repository.delete_session(token)
        audit("auth.logout", user_id=user["id"], resource_type="user", resource_id=user["id"], request=request)
        return Response(status_code=204)

    @app.get("/api/auth/me")
    def me(user: dict = Depends(current_user)) -> dict:
        return user

    @app.post("/api/analyses", status_code=201)
    def create_analysis(
        payload: AnalysisCreate,
        background_tasks: BackgroundTasks,
        request: Request,
        user: dict = Depends(current_user),
    ) -> dict:
        enforce_rate_limit("analysis", request, settings.analysis_rate_limit, user)
        task = service.create_analysis(user["id"], payload, run_inline=run_tasks_inline)
        audit("analysis.create", user_id=user["id"], resource_type="analysis", resource_id=task["id"], request=request)
        if not run_tasks_inline:
            background_tasks.add_task(service.run_task, task["id"], payload)
        return task

    @app.get("/api/analyses")
    @app.get("/api/history")
    def list_analyses(user: dict = Depends(current_user)) -> dict:
        return {"items": repository.list_tasks_for_user(user["id"])}

    @app.get("/api/analyses/{task_id}")
    @app.get("/api/history/{task_id}")
    def get_analysis(task_id: int, user: dict = Depends(current_user)) -> dict:
        task = repository.get_task_for_user(task_id, user["id"])
        if not task:
            raise HTTPException(status_code=404, detail="analysis not found")
        return task

    @app.post("/api/analyses/{task_id}/rerun", status_code=201)
    @app.post("/api/history/{task_id}/rerun", status_code=201)
    def rerun_analysis(
        task_id: int,
        payload: AnalysisRerun,
        background_tasks: BackgroundTasks,
        request: Request,
        user: dict = Depends(current_user),
    ) -> dict:
        enforce_rate_limit("analysis", request, settings.analysis_rate_limit, user)
        task = service.rerun(user["id"], task_id, payload, run_inline=run_tasks_inline)
        if not task:
            raise HTTPException(status_code=404, detail="analysis not found")
        audit(
            "analysis.rerun",
            user_id=user["id"],
            resource_type="analysis",
            resource_id=task["id"],
            metadata={"source_analysis_task_id": task_id},
            request=request,
        )
        if not run_tasks_inline:
            background_tasks.add_task(service.run_task, task["id"], AnalysisCreate(**task["parameters"]))
        return task

    @app.delete("/api/analyses/{task_id}", status_code=204)
    @app.delete("/api/history/{task_id}", status_code=204)
    def delete_analysis(task_id: int, request: Request, user: dict = Depends(current_user)) -> Response:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        if not repository.delete_task_for_user(task_id, user["id"]):
            raise HTTPException(status_code=404, detail="analysis not found")
        audit("analysis.delete", user_id=user["id"], resource_type="analysis", resource_id=task_id, request=request)
        return Response(status_code=204)

    @app.get("/api/account/export")
    def export_account(request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("export", request, settings.mutation_rate_limit, user)
        data = repository.export_user_data(user["id"])
        audit("account.export", user_id=user["id"], resource_type="account", resource_id=user["id"], request=request)
        return data

    @app.get("/api/account/audit")
    def list_account_audit(user: dict = Depends(current_user)) -> dict:
        return {"items": repository.list_audit_logs_for_user(user["id"])}

    @app.get("/api/interventions")
    def list_interventions(user: dict = Depends(current_user)) -> dict:
        return {"items": repository.list_interventions_for_user(user["id"])}

    @app.post("/api/interventions", status_code=201)
    def create_intervention(payload: InterventionCreate, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        session = repository.create_intervention_session(user["id"], payload.source_analysis_task_id, payload.target_agent_name)
        if not session:
            raise HTTPException(status_code=404, detail="analysis not found")
        audit(
            "intervention.create",
            user_id=user["id"],
            resource_type="intervention",
            resource_id=session["id"],
            metadata={"source_analysis_task_id": payload.source_analysis_task_id, "target_agent_name": payload.target_agent_name},
            request=request,
        )
        return session

    @app.get("/api/interventions/{session_id}")
    def get_intervention(session_id: int, user: dict = Depends(current_user)) -> dict:
        session = repository.get_intervention_for_user(session_id, user["id"])
        if not session:
            raise HTTPException(status_code=404, detail="intervention not found")
        return session

    @app.post("/api/interventions/{session_id}/messages", status_code=201)
    def append_intervention_message(session_id: int, payload: InterventionMessageCreate, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        if not repository.get_intervention_for_user(session_id, user["id"]):
            raise HTTPException(status_code=404, detail="intervention not found")
        message = repository.append_intervention_message(session_id, user["id"], payload.content)
        if not message:
            raise HTTPException(status_code=409, detail="intervention is not open")
        audit("intervention.message", user_id=user["id"], resource_type="intervention", resource_id=session_id, request=request)
        return message

    @app.post("/api/interventions/{session_id}/pause")
    def pause_intervention(session_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_intervention_for_user(session_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="intervention not found")
        if current["status"] == "closed":
            raise HTTPException(status_code=409, detail="intervention is closed")
        session = repository.set_intervention_status(session_id, user["id"], "paused")
        if not session:
            raise HTTPException(status_code=404, detail="intervention not found")
        audit("intervention.pause", user_id=user["id"], resource_type="intervention", resource_id=session_id, request=request)
        return session

    @app.post("/api/interventions/{session_id}/resume")
    def resume_intervention(session_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_intervention_for_user(session_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="intervention not found")
        if current["status"] == "closed":
            raise HTTPException(status_code=409, detail="intervention is closed")
        session = repository.set_intervention_status(session_id, user["id"], "open")
        if not session:
            raise HTTPException(status_code=404, detail="intervention not found")
        audit("intervention.resume", user_id=user["id"], resource_type="intervention", resource_id=session_id, request=request)
        return session

    @app.post("/api/interventions/{session_id}/close")
    def close_intervention(session_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        session = repository.set_intervention_status(session_id, user["id"], "closed")
        if not session:
            raise HTTPException(status_code=404, detail="intervention not found")
        audit("intervention.close", user_id=user["id"], resource_type="intervention", resource_id=session_id, request=request)
        return session

    @app.post("/api/interventions/{session_id}/run", status_code=201)
    def run_intervention(session_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("intervention", request, settings.intervention_rate_limit, user)
        if not repository.get_intervention_for_user(session_id, user["id"]):
            raise HTTPException(status_code=404, detail="intervention not found")
        output = intervention_service.run_continuation(session_id, user["id"])
        if not output:
            raise HTTPException(status_code=409, detail="intervention is not open")
        audit("intervention.run", user_id=user["id"], resource_type="intervention", resource_id=session_id, request=request)
        return output

    @app.delete("/api/interventions/{session_id}", status_code=204)
    def delete_intervention(session_id: int, request: Request, user: dict = Depends(current_user)) -> Response:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        if not repository.delete_intervention_for_user(session_id, user["id"]):
            raise HTTPException(status_code=404, detail="intervention not found")
        audit("intervention.delete", user_id=user["id"], resource_type="intervention", resource_id=session_id, request=request)
        return Response(status_code=204)

    @app.get("/api/memories")
    def list_memories(
        request: Request,
        ticker: str | None = None,
        agent: str | None = None,
        analysis_date: str | None = None,
        query: str | None = None,
        archived: bool | None = False,
        user: dict = Depends(current_user),
    ) -> dict:
        enforce_rate_limit("memory", request, settings.mutation_rate_limit, user)
        return {
            "items": repository.list_memories_for_user(
                user["id"],
                ticker=ticker,
                agent=agent,
                analysis_date=analysis_date,
                query=query,
                archived=archived,
            )
        }

    @app.get("/api/memories/{memory_id}")
    def get_memory(memory_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("memory", request, settings.mutation_rate_limit, user)
        memory = repository.get_memory_for_user(memory_id, user["id"])
        if not memory:
            raise HTTPException(status_code=404, detail="memory not found")
        return memory

    @app.patch("/api/memories/{memory_id}")
    def update_memory(memory_id: int, payload: MemoryUpdate, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        memory = repository.update_memory(memory_id, user["id"], payload)
        if not memory:
            raise HTTPException(status_code=404, detail="memory not found")
        audit("memory.update", user_id=user["id"], resource_type="memory", resource_id=memory_id, request=request)
        return memory

    @app.post("/api/memories/{memory_id}/archive")
    def archive_memory(memory_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        memory = repository.set_memory_archived(memory_id, user["id"], True)
        if not memory:
            raise HTTPException(status_code=404, detail="memory not found")
        audit("memory.archive", user_id=user["id"], resource_type="memory", resource_id=memory_id, request=request)
        return memory

    @app.post("/api/memories/{memory_id}/unarchive")
    def unarchive_memory(memory_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        memory = repository.set_memory_archived(memory_id, user["id"], False)
        if not memory:
            raise HTTPException(status_code=404, detail="memory not found")
        audit("memory.unarchive", user_id=user["id"], resource_type="memory", resource_id=memory_id, request=request)
        return memory

    @app.post("/api/schedules", status_code=201)
    def create_schedule(payload: ScheduledAnalysisCreate, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        schedule = scheduler_service.create_schedule(user["id"], payload)
        audit("schedule.create", user_id=user["id"], resource_type="schedule", resource_id=schedule["id"], request=request)
        return schedule

    @app.get("/api/schedules")
    def list_schedules(user: dict = Depends(current_user)) -> dict:
        return {"items": repository.list_schedules_for_user(user["id"])}

    @app.get("/api/schedules/{schedule_id}")
    def get_schedule(schedule_id: int, user: dict = Depends(current_user)) -> dict:
        schedule = repository.get_schedule_for_user(schedule_id, user["id"])
        if not schedule:
            raise HTTPException(status_code=404, detail="schedule not found")
        return schedule

    @app.patch("/api/schedules/{schedule_id}")
    def update_schedule(schedule_id: int, payload: ScheduledAnalysisUpdate, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        schedule = repository.update_schedule(schedule_id, user["id"], payload)
        if not schedule:
            raise HTTPException(status_code=404, detail="schedule not found")
        audit("schedule.update", user_id=user["id"], resource_type="schedule", resource_id=schedule_id, request=request)
        return schedule

    @app.delete("/api/schedules/{schedule_id}", status_code=204)
    def delete_schedule(schedule_id: int, request: Request, user: dict = Depends(current_user)) -> Response:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        if not repository.delete_schedule(schedule_id, user["id"]):
            raise HTTPException(status_code=404, detail="schedule not found")
        audit("schedule.delete", user_id=user["id"], resource_type="schedule", resource_id=schedule_id, request=request)
        return Response(status_code=204)

    @app.post("/api/schedules/{schedule_id}/pause")
    def pause_schedule(schedule_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        schedule = repository.set_schedule_status(schedule_id, user["id"], "paused")
        if not schedule:
            raise HTTPException(status_code=404, detail="schedule not found")
        audit("schedule.pause", user_id=user["id"], resource_type="schedule", resource_id=schedule_id, request=request)
        return schedule

    @app.post("/api/schedules/{schedule_id}/resume")
    def resume_schedule(schedule_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        schedule = repository.set_schedule_status(schedule_id, user["id"], "active")
        if not schedule:
            raise HTTPException(status_code=404, detail="schedule not found")
        audit("schedule.resume", user_id=user["id"], resource_type="schedule", resource_id=schedule_id, request=request)
        return schedule

    @app.post("/api/schedules/{schedule_id}/trigger", status_code=201)
    def trigger_schedule(schedule_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        execution = scheduler_service.execute_schedule(user["id"], schedule_id, run_inline=run_tasks_inline, triggered_by="manual")
        if not execution:
            raise HTTPException(status_code=404, detail="schedule not found")
        audit(
            "schedule.trigger",
            user_id=user["id"],
            resource_type="schedule",
            resource_id=schedule_id,
            metadata={"execution_id": execution["id"], "analysis_task_id": execution.get("analysis_task_id")},
            request=request,
        )
        return execution

    @app.post("/api/scheduler/run-due")
    def run_due_schedules(payload: RunDueRequest, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        now = format_iso_datetime(payload.now) if payload.now else None
        executions = scheduler_service.run_due_for_user(user["id"], now=now, run_inline=run_tasks_inline)
        audit(
            "schedule.run_due",
            user_id=user["id"],
            resource_type="schedule",
            metadata={"executed": len(executions), "execution_ids": [execution["id"] for execution in executions]},
            request=request,
        )
        return {"executed": len(executions), "executions": executions}

    def event_stream(task_id: int, user: dict) -> StreamingResponse:
        task = repository.get_task_for_user(task_id, user["id"])
        if not task:
            raise HTTPException(status_code=404, detail="analysis not found")

        def generate() -> Iterator[str]:
            last_sequence = 0
            while True:
                current = repository.get_task_for_user(task_id, user["id"])
                if not current:
                    yield "event: end\ndata: {}\n\n"
                    return
                for event in current["events"]:
                    if event["sequence"] > last_sequence:
                        last_sequence = event["sequence"]
                        yield f"id: {event['sequence']}\nevent: task_event\ndata: {json.dumps(event)}\n\n"
                if current["status"] in {"completed", "failed"}:
                    yield "event: end\ndata: {}\n\n"
                    return
                time.sleep(0.25)

        return StreamingResponse(generate(), media_type="text/event-stream")

    @app.get("/api/analyses/{task_id}/events")
    @app.get("/api/analyses/{task_id}/events/stream")
    def events(task_id: int, user: dict = Depends(current_user)) -> StreamingResponse:
        return event_stream(task_id, user)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = WebSettings()
    uvicorn.run("tradingagents.web.main:app", host=settings.host, port=settings.port, reload=False)
