from __future__ import annotations

import json
import time
from collections.abc import Iterator
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlite3 import IntegrityError

from .database import WebRepository
from .runner import DemoAnalysisRunner, TradingAgentsGraphRunner
from .schemas import AnalysisCreate, AnalysisRerun, LoginRequest, TokenResponse, UserCreate
from .service import AnalysisService
from .settings import WebSettings

security = HTTPBearer(auto_error=False)


def create_app(settings: WebSettings | None = None, *, run_tasks_inline: bool = False) -> FastAPI:
    settings = settings or WebSettings()
    repository = WebRepository(settings.database_path)
    runner = DemoAnalysisRunner() if settings.runner_mode == "demo" else TradingAgentsGraphRunner()
    service = AnalysisService(repository, runner)
    app = FastAPI(title="TradingAgents Web", version="0.1.0")
    app.state.settings = settings
    app.state.repository = repository
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

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
    def register(payload: UserCreate) -> dict:
        if not settings.allow_registration:
            raise HTTPException(status_code=403, detail="registration disabled")
        try:
            return repository.create_user(payload.email, payload.password)
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="user already exists") from exc

    @app.post("/api/auth/login", response_model=TokenResponse)
    def login(payload: LoginRequest) -> dict:
        user = repository.authenticate(payload.email, payload.password)
        if not user:
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = repository.create_session(user["id"])
        return {"access_token": token, "token_type": "bearer", "user": user}

    @app.post("/api/auth/logout", status_code=204)
    def logout(token: str = Depends(current_token), user: dict = Depends(current_user)) -> Response:
        repository.delete_session(token)
        return Response(status_code=204)

    @app.get("/api/auth/me")
    def me(user: dict = Depends(current_user)) -> dict:
        return user

    @app.post("/api/analyses", status_code=201)
    def create_analysis(payload: AnalysisCreate, background_tasks: BackgroundTasks, user: dict = Depends(current_user)) -> dict:
        task = service.create_analysis(user["id"], payload, run_inline=run_tasks_inline)
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
    def rerun_analysis(task_id: int, payload: AnalysisRerun, background_tasks: BackgroundTasks, user: dict = Depends(current_user)) -> dict:
        task = service.rerun(user["id"], task_id, payload, run_inline=run_tasks_inline)
        if not task:
            raise HTTPException(status_code=404, detail="analysis not found")
        if not run_tasks_inline:
            background_tasks.add_task(service.run_task, task["id"], AnalysisCreate(**task["parameters"]))
        return task

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
