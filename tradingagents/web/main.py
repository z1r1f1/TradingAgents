from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import datetime, timezone
import requests
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlite3 import IntegrityError

from .coordination import InMemoryCoordinator, RedisCoordinator
from .database import WebRepository
from .intervention import InterventionService
from .postgres import PostgresWebRepository
from .runner import DemoAnalysisRunner, TradingAgentsGraphRunner
from .schemas import (
    AnalysisCreate,
    AnalysisRerun,
    InterventionCreate,
    InterventionMessageCreate,
    LegalHoldCreate,
    LegalHoldRelease,
    LoginRequest,
    OidcCallbackRequest,
    ProvisioningUserCreate,
    ProvisioningUserUpdate,
    RetentionPolicyRequest,
    RunDueRequest,
    ScheduledAnalysisCreate,
    ScheduledAnalysisUpdate,
    MemoryUpdate,
    TokenResponse,
    UserCreate,
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceMemberUpdate,
)
from .scheduler import SchedulerService, format_iso_datetime
from .service import AnalysisService
from .settings import WebSettings

security = HTTPBearer(auto_error=False)

EASTMONEY_STOCK_SEARCH_URL = "https://searchapi.eastmoney.com/api/suggest/get"


def normalize_eastmoney_stock_suggestions(payload: dict, *, limit: int = 8) -> list[dict]:
    rows = payload.get("QuotationCodeTable", {}).get("Data", [])
    suggestions: list[dict] = []
    market_suffix = {"1": ".SS", "0": ".SZ"}
    for row in rows:
        code = str(row.get("Code") or "").strip()
        name = str(row.get("Name") or "").strip()
        mkt_num = str(row.get("MktNum") or "").strip()
        suffix = market_suffix.get(mkt_num)
        if not code or not name or not suffix:
            continue
        if row.get("Classify") and row.get("Classify") != "AStock":
            continue
        suggestions.append(
            {
                "code": code,
                "name": name,
                "ticker": f"{code}{suffix}",
                "market": str(row.get("SecurityTypeName") or ("沪A" if suffix == ".SS" else "深A")),
                "pinyin": str(row.get("PinYin") or ""),
            }
        )
        if len(suggestions) >= limit:
            break
    return suggestions


def create_app(settings: WebSettings | None = None, *, run_tasks_inline: bool = False, coordinator=None) -> FastAPI:
    settings = settings or WebSettings()
    settings.validate_for_startup()
    repository = PostgresWebRepository(settings.postgres_dsn) if settings.runtime_mode == "production-cluster" and settings.postgres_dsn else WebRepository(settings.database_path)
    if coordinator is None:
        coordinator = (
            RedisCoordinator(settings.redis_url, namespace=settings.coordination_namespace)
            if settings.runtime_mode == "production-cluster" and settings.redis_url
            else InMemoryCoordinator(namespace=settings.coordination_namespace)
        )
    coordinator.check_health()
    if settings.bootstrap_user_email and settings.bootstrap_user_password and not repository.get_user_by_email(settings.bootstrap_user_email):
        user = repository.create_user(settings.bootstrap_user_email, settings.bootstrap_user_password)
        repository.append_audit_log("auth.user.provisioned", user_id=user["id"], resource_type="user", resource_id=user["id"])
    if settings.runtime_mode != "production-cluster":
        recovered = repository.fail_interrupted_active_tasks()
        if recovered:
            repository.append_audit_log(
                "analysis.recovered_interrupted",
                metadata={"count": recovered, "reason": "analysis interrupted by server restart"},
            )
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
    app.state.coordinator = coordinator
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    @app.on_event("startup")
    def start_analysis_queue() -> None:
        if run_tasks_inline:
            return
        service.start_queue(max_workers=settings.analysis_workers)
        for queued_task in repository.list_queued_analysis_tasks():
            service.enqueue_task(queued_task["id"], AnalysisCreate(**queued_task["parameters"]))

    @app.on_event("shutdown")
    def stop_analysis_queue() -> None:
        service.stop_queue()

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
        workspace_id: int | None = None,
        metadata: dict | None = None,
        request: Request | None = None,
    ) -> None:
        repository.append_audit_log(
            event_type,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            workspace_id=workspace_id,
            metadata=metadata,
            ip_address=request_ip(request),
        )

    def workspace_role(user: dict, workspace_id: int | None) -> tuple[int, str]:
        resolved = repository.resolve_workspace_id(user["id"], workspace_id)
        role = repository.get_workspace_role(user["id"], resolved)
        if not role:
            raise HTTPException(status_code=404, detail="workspace not found")
        return resolved, role

    def require_workspace_role(user: dict, workspace_id: int | None, allowed: set[str]) -> tuple[int, str]:
        resolved, role = workspace_role(user, workspace_id)
        if role not in allowed:
            raise HTTPException(status_code=403, detail="workspace role is not allowed")
        return resolved, role

    def enforce_real_runner_budget(user: dict, workspace_id: int, request: Request) -> None:
        if settings.runner_mode == "demo":
            return
        if settings.real_runner_user_analysis_limit >= 0 and repository.count_analysis_tasks(user_id=user["id"]) >= settings.real_runner_user_analysis_limit:
            audit(
                "cost.blocked",
                user_id=user["id"],
                workspace_id=workspace_id,
                resource_type="analysis",
                metadata={"reason": "user budget exceeded"},
                request=request,
            )
            raise HTTPException(status_code=402, detail="user real-runner budget exceeded")
        if (
            settings.real_runner_workspace_analysis_limit >= 0
            and repository.count_analysis_tasks(workspace_id=workspace_id) >= settings.real_runner_workspace_analysis_limit
        ):
            audit(
                "cost.blocked",
                user_id=user["id"],
                workspace_id=workspace_id,
                resource_type="analysis",
                metadata={"reason": "workspace budget exceeded"},
                request=request,
            )
            raise HTTPException(status_code=402, detail="workspace real-runner budget exceeded")
        decision = coordinator.try_consume_budget(
            user_id=user["id"],
            workspace_id=workspace_id,
            user_limit=settings.real_runner_user_analysis_limit,
            workspace_limit=settings.real_runner_workspace_analysis_limit,
        )
        if decision.allowed:
            budget_period = getattr(settings, "real_runner_budget_period", "never")
            repository.record_usage_ledger(
                user_id=user["id"],
                workspace_id=workspace_id,
                resource_type="analysis",
                event_type="budget.usage.recorded",
                allowed=True,
                request_kind="analysis",
                period_kind=budget_period,
            )
        if not decision.allowed:
            audit(
                "cost.blocked",
                user_id=user["id"],
                workspace_id=workspace_id,
                resource_type="analysis",
                metadata={"reason": decision.reason, "coordinator": coordinator.backend_name},
                request=request,
            )
            raise HTTPException(status_code=402, detail=decision.reason or "real-runner budget exceeded")

    def analysis_is_active(status_value: str | None) -> bool:
        return status_value in {"queued", "running", "pending"}

    def parse_event_time(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def annotate_analysis_runtime(task: dict, stale_after_seconds: int | None = None) -> dict:
        threshold = stale_after_seconds if stale_after_seconds is not None else settings.analysis_stale_after_seconds
        last_event = parse_event_time(task.get("last_event_at"))
        seconds_since_last_event = None
        if last_event is not None:
            if last_event.tzinfo is None:
                last_event = last_event.replace(tzinfo=timezone.utc)
            seconds_since_last_event = max(0, int((datetime.now(timezone.utc) - last_event).total_seconds()))
        task["stale_after_seconds"] = threshold
        task["seconds_since_last_event"] = seconds_since_last_event
        task["stale"] = bool(analysis_is_active(task.get("status")) and seconds_since_last_event is not None and seconds_since_last_event >= threshold)
        return task

    def rate_identity(request: Request, user: dict | None = None) -> str:
        if user:
            return f"user:{user['id']}"
        return f"ip:{request_ip(request) or 'unknown'}"

    def enforce_rate_limit(scope: str, request: Request, limit: int, user: dict | None = None) -> None:
        if limit <= 0:
            return
        decision = coordinator.check_rate_limit(
            scope,
            rate_identity(request, user),
            limit=limit,
            window_seconds=settings.rate_limit_window_seconds,
        )
        if not decision.allowed:
            audit("rate_limit.exceeded", user_id=user["id"] if user else None, resource_type=scope, request=request)
            raise HTTPException(status_code=429, detail=decision.reason or "rate limit exceeded")

    def idempotency_cache_key(request: Request, user: dict, scope: str) -> str | None:
        key = request.headers.get("Idempotency-Key")
        if not key:
            return None
        return f"{scope}:user:{user['id']}:{key}"

    def get_idempotent_response(request: Request, user: dict, scope: str) -> tuple[str | None, dict | None]:
        key = idempotency_cache_key(request, user, scope)
        if not key:
            return None, None
        response = coordinator.get_idempotent_response(key)
        if response is not None:
            audit(
                "idempotency.replay",
                user_id=user["id"],
                workspace_id=response.get("workspace_id"),
                resource_type=scope,
                resource_id=response.get("id"),
                metadata={"key": key},
                request=request,
            )
        return key, response

    def store_idempotent_response(key: str | None, response: dict) -> None:
        if key:
            coordinator.store_idempotent_response(key, response, ttl_seconds=24 * 60 * 60)

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

    def oidc_discovery_url() -> str:
        return f"{settings.oidc_issuer_url.rstrip('/')}/.well-known/openid-configuration"  # type: ignore[union-attr]

    def oidc_groups_from_userinfo(userinfo: dict) -> list[str]:
        raw_groups = userinfo.get(settings.oidc_group_claim, [])
        if isinstance(raw_groups, str):
            return [raw_groups]
        if isinstance(raw_groups, list):
            return [str(group) for group in raw_groups if str(group).strip()]
        return []

    def oidc_public_status() -> dict:
        authorization_endpoint = settings.oidc_authorization_endpoint
        if settings.oidc_enabled and not authorization_endpoint and settings.oidc_issuer_url:
            authorization_endpoint = f"{settings.oidc_issuer_url.rstrip('/')}/authorize"
        return {
            "oidc_enabled": settings.oidc_enabled,
            "issuer_url": settings.oidc_issuer_url if settings.oidc_enabled else None,
            "authorization_endpoint": authorization_endpoint if settings.oidc_enabled else None,
            "client_id": settings.oidc_client_id if settings.oidc_enabled else None,
            "redirect_uri": settings.oidc_redirect_uri if settings.oidc_enabled else None,
            "scope": settings.oidc_scope if settings.oidc_enabled else None,
            "group_claim": settings.oidc_group_claim,
            "mapped_groups": sorted(settings.oidc_group_role_mapping.keys()) if settings.oidc_enabled else [],
        }

    def oidc_live_health() -> dict:
        if not settings.oidc_enabled or not settings.oidc_issuer_url:
            return {"ok": False, "oidc_enabled": settings.oidc_enabled, "checks": [], "reason": "OIDC is disabled"}
        checks: list[dict] = []
        try:
            discovery_response = requests.get(oidc_discovery_url(), timeout=10)
            discovery_ok = 200 <= getattr(discovery_response, "status_code", 200) < 500
            discovery = discovery_response.json() if discovery_ok else {}
            checks.append({"name": "discovery", "ok": discovery_ok, "status_code": getattr(discovery_response, "status_code", None)})
            userinfo_endpoint = discovery.get("userinfo_endpoint") if isinstance(discovery, dict) else None
            if userinfo_endpoint:
                userinfo_response = requests.get(userinfo_endpoint, timeout=10)
                userinfo_status = getattr(userinfo_response, "status_code", 200)
                checks.append({"name": "userinfo", "ok": userinfo_status < 500, "status_code": userinfo_status})
            else:
                checks.append({"name": "userinfo", "ok": False, "status_code": None, "reason": "missing userinfo_endpoint"})
        except Exception as exc:
            checks.append({"name": "provider", "ok": False, "reason": exc.__class__.__name__})
        return {
            "ok": all(check.get("ok") for check in checks),
            "oidc_enabled": True,
            "issuer_url": settings.oidc_issuer_url,
            "checks": checks,
        }

    @app.get("/health")
    @app.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "bind_host": settings.host,
            "runtime_mode": settings.runtime_mode,
            "storage_backend": getattr(repository, "storage_backend", "sqlite"),
            "coordination_backend": coordinator.backend_name,
            "postgres_configured": bool(settings.postgres_dsn),
            "redis_configured": bool(settings.redis_url),
            "coordination": coordinator.check_health(),
        }

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

    @app.get("/api/auth/oidc/status")
    def auth_oidc_status() -> dict:
        return oidc_public_status()

    @app.post("/api/auth/oidc/callback", response_model=TokenResponse)
    def oidc_callback(payload: OidcCallbackRequest, request: Request) -> dict:
        enforce_rate_limit("auth", request, settings.auth_rate_limit)
        if not settings.oidc_enabled:
            raise HTTPException(status_code=404, detail="OIDC login is disabled")
        redirect_uri = payload.redirect_uri or settings.oidc_redirect_uri
        if redirect_uri != settings.oidc_redirect_uri:
            audit("auth.oidc.failure", metadata={"reason": "redirect_uri mismatch", "issuer": settings.oidc_issuer_url}, request=request)
            raise HTTPException(status_code=400, detail="OIDC redirect_uri mismatch")
        try:
            discovery = requests.get(oidc_discovery_url(), timeout=10).json()
            token_response = requests.post(
                discovery["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": payload.code,
                    "redirect_uri": redirect_uri,
                    "client_id": settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret,
                },
                timeout=10,
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
            access_token = token_payload.get("access_token")
            if not access_token:
                raise ValueError("missing access token")
            userinfo_response = requests.get(
                discovery["userinfo_endpoint"],
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            userinfo_response.raise_for_status()
            userinfo = userinfo_response.json()
            subject = str(userinfo.get("sub") or "").strip()
            email = str(userinfo.get("email") or "").strip().lower()
            if not subject or "@" not in email:
                raise ValueError("OIDC userinfo must include sub and email")
            groups = oidc_groups_from_userinfo(userinfo)
            user, action = repository.upsert_oidc_user(issuer=settings.oidc_issuer_url or "", subject=subject, email=email, groups=groups)
            mappings = repository.apply_oidc_group_mappings(
                user_id=user["id"],
                groups=groups,
                mapping=settings.oidc_group_role_mapping,
            )
            token = repository.create_session(user["id"])
            audit(
                f"auth.oidc.{action}",
                user_id=user["id"],
                resource_type="user",
                resource_id=user["id"],
                metadata={"issuer": settings.oidc_issuer_url, "subject": subject, "groups": groups, "mappings": mappings},
                request=request,
            )
            audit("auth.oidc.success", user_id=user["id"], resource_type="user", resource_id=user["id"], metadata={"issuer": settings.oidc_issuer_url}, request=request)
            return {"access_token": token, "token_type": "bearer", "user": user}
        except HTTPException:
            raise
        except Exception as exc:
            audit("auth.oidc.failure", metadata={"reason": exc.__class__.__name__, "issuer": settings.oidc_issuer_url}, request=request)
            raise HTTPException(status_code=401, detail="OIDC login failed") from exc

    @app.post("/api/auth/logout", status_code=204)
    def logout(request: Request, token: str = Depends(current_token), user: dict = Depends(current_user)) -> Response:
        repository.delete_session(token)
        audit("auth.logout", user_id=user["id"], resource_type="user", resource_id=user["id"], request=request)
        return Response(status_code=204)

    @app.get("/api/auth/me")
    def me(user: dict = Depends(current_user)) -> dict:
        return user

    @app.get("/api/identity/status")
    def identity_status(user: dict = Depends(current_user)) -> dict:
        return oidc_public_status()

    @app.get("/api/identity/users")
    def identity_users(workspace_id: int | None = None, user: dict = Depends(current_user)) -> dict:
        if workspace_id is not None:
            require_workspace_role(user, workspace_id, {"owner", "admin"})
        return {"items": repository.list_identity_links(workspace_id=workspace_id)}

    @app.get("/api/identity/idp-health")
    def identity_idp_health(workspace_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        require_workspace_role(user, workspace_id, {"owner", "admin"})
        result = oidc_live_health()
        audit(
            "identity.idp_health",
            user_id=user["id"],
            workspace_id=workspace_id,
            resource_type="identity_provider",
            metadata={"ok": result["ok"], "issuer_url": result.get("issuer_url"), "checks": result.get("checks", [])},
            request=request,
        )
        return result

    @app.get("/api/provisioning/events")
    def provisioning_events(workspace_id: int, user: dict = Depends(current_user)) -> dict:
        require_workspace_role(user, workspace_id, {"owner", "admin"})
        return {"items": repository.list_provisioning_events(workspace_id=workspace_id)}

    @app.post("/api/provisioning/users", status_code=201)
    def provision_user(payload: ProvisioningUserCreate, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        require_workspace_role(user, payload.workspace_id, {"owner", "admin"})
        try:
            member = repository.provision_workspace_user(
                workspace_id=payload.workspace_id,
                email=payload.email,
                role=payload.role,
                actor_user_id=user["id"],
                external_id=payload.external_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        audit(
            "provisioning.user.provision",
            user_id=user["id"],
            workspace_id=payload.workspace_id,
            resource_type="workspace_member",
            resource_id=member["user_id"],
            metadata={"role": payload.role, "external_id": payload.external_id},
            request=request,
        )
        return member

    @app.patch("/api/provisioning/workspaces/{workspace_id}/users/{target_user_id}")
    def update_provisioned_user(
        workspace_id: int,
        target_user_id: int,
        payload: ProvisioningUserUpdate,
        request: Request,
        user: dict = Depends(current_user),
    ) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        require_workspace_role(user, workspace_id, {"owner", "admin"})
        try:
            member = repository.update_provisioned_workspace_user(
                workspace_id=workspace_id,
                target_user_id=target_user_id,
                actor_user_id=user["id"],
                role=payload.role,
                active=payload.active,
                external_id=payload.external_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        audit(
            "provisioning.user.update",
            user_id=user["id"],
            workspace_id=workspace_id,
            resource_type="workspace_member",
            resource_id=target_user_id,
            metadata={"role": payload.role, "active": payload.active, "external_id": payload.external_id},
            request=request,
        )
        return member

    @app.get("/api/workspaces")
    def list_workspaces(user: dict = Depends(current_user)) -> dict:
        return {"items": repository.list_workspaces_for_user(user["id"])}

    @app.post("/api/workspaces", status_code=201)
    def create_workspace(payload: WorkspaceCreate, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        workspace = repository.create_workspace(user["id"], payload.name)
        audit("workspace.create", user_id=user["id"], workspace_id=workspace["id"], resource_type="workspace", resource_id=workspace["id"], request=request)
        return workspace

    @app.get("/api/workspaces/{workspace_id}")
    def get_workspace(workspace_id: int, user: dict = Depends(current_user)) -> dict:
        workspace = repository.get_workspace_for_user(workspace_id, user["id"])
        if not workspace:
            raise HTTPException(status_code=404, detail="workspace not found")
        return workspace

    @app.post("/api/workspaces/{workspace_id}/members", status_code=201)
    def add_workspace_member(workspace_id: int, payload: WorkspaceMemberCreate, request: Request, user: dict = Depends(current_user)) -> dict:
        require_workspace_role(user, workspace_id, {"owner", "admin"})
        member = repository.add_workspace_member(workspace_id, payload.email, payload.role)
        if not member:
            raise HTTPException(status_code=404, detail="user not found")
        audit(
            "workspace.member.add",
            user_id=user["id"],
            workspace_id=workspace_id,
            resource_type="workspace_member",
            resource_id=member["user_id"],
            metadata={"role": payload.role},
            request=request,
        )
        return member

    @app.patch("/api/workspaces/{workspace_id}/members/{member_user_id}")
    def update_workspace_member(workspace_id: int, member_user_id: int, payload: WorkspaceMemberUpdate, request: Request, user: dict = Depends(current_user)) -> dict:
        require_workspace_role(user, workspace_id, {"owner", "admin"})
        try:
            member = repository.update_workspace_member_role(workspace_id, member_user_id, payload.role)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if not member:
            raise HTTPException(status_code=404, detail="workspace member not found")
        audit(
            "workspace.member.role",
            user_id=user["id"],
            workspace_id=workspace_id,
            resource_type="workspace_member",
            resource_id=member_user_id,
            metadata={"role": payload.role},
            request=request,
        )
        return member

    @app.delete("/api/workspaces/{workspace_id}/members/{member_user_id}", status_code=204)
    def remove_workspace_member(workspace_id: int, member_user_id: int, request: Request, user: dict = Depends(current_user)) -> Response:
        require_workspace_role(user, workspace_id, {"owner", "admin"})
        if not repository.remove_workspace_member(workspace_id, member_user_id):
            raise HTTPException(status_code=409, detail="workspace member cannot be removed")
        audit("workspace.member.remove", user_id=user["id"], workspace_id=workspace_id, resource_type="workspace_member", resource_id=member_user_id, request=request)
        return Response(status_code=204)

    @app.get("/api/stock-search")
    def search_stocks(query: str = "", user: dict = Depends(current_user)) -> dict:
        del user
        query = query.strip()
        if not query:
            return {"items": []}
        try:
            response = requests.get(
                EASTMONEY_STOCK_SEARCH_URL,
                params={"input": query, "type": "14"},
                timeout=8,
            )
            response.raise_for_status()
            return {"items": normalize_eastmoney_stock_suggestions(response.json())}
        except Exception:
            return {"items": []}

    @app.post("/api/analyses", status_code=201)
    def create_analysis(
        payload: AnalysisCreate,
        request: Request,
        user: dict = Depends(current_user),
    ) -> dict:
        enforce_rate_limit("analysis", request, settings.analysis_rate_limit, user)
        idem_key, cached = get_idempotent_response(request, user, "analysis.create")
        if cached is not None:
            return cached
        workspace_id, _ = require_workspace_role(user, payload.workspace_id, {"owner", "admin", "member"})
        payload = payload.model_copy(update={"workspace_id": workspace_id})
        enforce_real_runner_budget(user, workspace_id, request)
        task = service.create_analysis(user["id"], payload, run_inline=run_tasks_inline)
        repository.update_latest_usage_ledger_resource(user_id=user["id"], workspace_id=workspace_id, resource_type="analysis", resource_id=task["id"])
        audit("analysis.create", user_id=user["id"], workspace_id=workspace_id, resource_type="analysis", resource_id=task["id"], request=request)
        if not run_tasks_inline:
            service.enqueue_task(task["id"], payload)
        store_idempotent_response(idem_key, task)
        return task

    @app.get("/api/analyses")
    @app.get("/api/history")
    def list_analyses(workspace_id: int | None = None, user: dict = Depends(current_user)) -> dict:
        if workspace_id is not None:
            require_workspace_role(user, workspace_id, {"owner", "admin", "member", "viewer"})
        return {"items": [annotate_analysis_runtime(item) for item in repository.list_tasks_for_user(user["id"], workspace_id)]}

    @app.get("/api/analyses/{task_id}")
    @app.get("/api/history/{task_id}")
    def get_analysis(task_id: int, stale_after_seconds: int | None = None, user: dict = Depends(current_user)) -> dict:
        task = repository.get_task_for_user(task_id, user["id"])
        if not task:
            raise HTTPException(status_code=404, detail="analysis not found")
        return annotate_analysis_runtime(task, stale_after_seconds)

    @app.post("/api/analyses/{task_id}/cancel")
    def cancel_analysis(task_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_task_for_user(task_id, user["id"], include_detail=False)
        if not current:
            raise HTTPException(status_code=404, detail="analysis not found")
        workspace_id = current.get("workspace_id")
        require_workspace_role(user, workspace_id, {"owner", "admin", "member"})
        task = repository.cancel_task_for_user(task_id, user["id"])
        if not task:
            raise HTTPException(status_code=409, detail="analysis is not running")
        audit("analysis.cancel", user_id=user["id"], workspace_id=workspace_id, resource_type="analysis", resource_id=task_id, request=request)
        return annotate_analysis_runtime(task)

    @app.post("/api/analyses/{task_id}/pause")
    def pause_analysis(task_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_task_for_user(task_id, user["id"], include_detail=False)
        if not current:
            raise HTTPException(status_code=404, detail="analysis not found")
        workspace_id = current.get("workspace_id")
        require_workspace_role(user, workspace_id, {"owner", "admin", "member"})
        task = repository.pause_task_for_user(task_id, user["id"])
        if not task:
            raise HTTPException(status_code=409, detail="analysis is not running")
        audit("analysis.pause", user_id=user["id"], workspace_id=workspace_id, resource_type="analysis", resource_id=task_id, request=request)
        return annotate_analysis_runtime(task)

    @app.post("/api/analyses/{task_id}/rerun", status_code=201)
    @app.post("/api/history/{task_id}/rerun", status_code=201)
    def rerun_analysis(
        task_id: int,
        payload: AnalysisRerun,
        request: Request,
        user: dict = Depends(current_user),
    ) -> dict:
        enforce_rate_limit("analysis", request, settings.analysis_rate_limit, user)
        idem_key, cached = get_idempotent_response(request, user, f"analysis.rerun:{task_id}")
        if cached is not None:
            return cached
        source = repository.get_task_for_user(task_id, user["id"], include_detail=False)
        if not source:
            raise HTTPException(status_code=404, detail="analysis not found")
        workspace_id, _ = require_workspace_role(user, payload.workspace_id or source.get("workspace_id"), {"owner", "admin", "member"})
        payload = payload.model_copy(update={"workspace_id": workspace_id})
        enforce_real_runner_budget(user, workspace_id, request)
        task = service.rerun(user["id"], task_id, payload, run_inline=run_tasks_inline)
        if not task:
            raise HTTPException(status_code=404, detail="analysis not found")
        audit(
            "analysis.rerun",
            user_id=user["id"],
            workspace_id=workspace_id,
            resource_type="analysis",
            resource_id=task["id"],
            metadata={"source_analysis_task_id": task_id},
            request=request,
        )
        if not run_tasks_inline:
            service.enqueue_task(task["id"], AnalysisCreate(**task["parameters"]))
        store_idempotent_response(idem_key, task)
        return task

    @app.delete("/api/analyses/{task_id}", status_code=204)
    @app.delete("/api/history/{task_id}", status_code=204)
    def delete_analysis(task_id: int, request: Request, user: dict = Depends(current_user)) -> Response:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        task = repository.get_task_for_user(task_id, user["id"], include_detail=False)
        if not task:
            raise HTTPException(status_code=404, detail="analysis not found")
        if analysis_is_active(task.get("status")):
            raise HTTPException(status_code=409, detail="cancel or wait for analysis before deleting it")
        require_workspace_role(user, task.get("workspace_id"), {"owner", "admin"})
        if not repository.delete_task_for_user(task_id, user["id"]):
            raise HTTPException(status_code=404, detail="analysis not found")
        audit("analysis.delete", user_id=user["id"], workspace_id=task.get("workspace_id"), resource_type="analysis", resource_id=task_id, request=request)
        return Response(status_code=204)

    @app.get("/api/account/export")
    def export_account(request: Request, workspace_id: int | None = None, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("export", request, settings.mutation_rate_limit, user)
        if workspace_id is not None:
            require_workspace_role(user, workspace_id, {"owner", "admin", "member", "viewer"})
        data = repository.export_user_data(user["id"], workspace_id)
        audit("account.export", user_id=user["id"], workspace_id=workspace_id, resource_type="account", resource_id=user["id"], request=request)
        return data

    @app.get("/api/account/audit")
    def list_account_audit(user: dict = Depends(current_user)) -> dict:
        return {"items": repository.list_audit_logs_for_user(user["id"])}

    @app.get("/api/governance/audit")
    def governance_audit(
        workspace_id: int | None = None,
        user_id: int | None = None,
        event_type: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
        user: dict = Depends(current_user),
    ) -> dict:
        if workspace_id is not None:
            require_workspace_role(user, workspace_id, {"owner", "admin", "member", "viewer"})
        return {
            "items": repository.list_audit_logs_for_user(
                user["id"],
                workspace_id=workspace_id,
                target_user_id=user_id,
                event_type=event_type,
                start_at=start_at,
                end_at=end_at,
            )
        }

    def validate_retention_policy(payload: RetentionPolicyRequest) -> None:
        if payload.resource_type == "audit_logs" and not payload.include_audit_logs:
            raise HTTPException(status_code=400, detail="audit log retention requires explicit include_audit_logs=true")
        if payload.resource_type == "usage_ledger" and not payload.include_usage_ledger:
            raise HTTPException(status_code=400, detail="usage ledger retention requires explicit include_usage_ledger=true")

    @app.post("/api/governance/retention/preview")
    def retention_preview(payload: RetentionPolicyRequest, request: Request, user: dict = Depends(current_user)) -> dict:
        require_workspace_role(user, payload.workspace_id, {"owner", "admin"})
        validate_retention_policy(payload)
        cutoff = payload.cutoff_before.isoformat()
        result = repository.retention_preview(
            workspace_id=payload.workspace_id,
            resource_type=payload.resource_type,
            cutoff_before=cutoff,
        )
        audit(
            "retention.preview",
            user_id=user["id"],
            workspace_id=payload.workspace_id,
            resource_type="retention_policy",
            metadata={**result, "archive_memories": payload.archive_memories},
            request=request,
        )
        return result

    @app.post("/api/governance/retention/apply")
    def retention_apply(payload: RetentionPolicyRequest, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        require_workspace_role(user, payload.workspace_id, {"owner", "admin"})
        validate_retention_policy(payload)
        cutoff = payload.cutoff_before.isoformat()
        result = repository.retention_apply(
            workspace_id=payload.workspace_id,
            resource_type=payload.resource_type,
            cutoff_before=cutoff,
            archive_memories=payload.archive_memories,
        )
        audit(
            "retention.apply",
            user_id=user["id"],
            workspace_id=payload.workspace_id,
            resource_type="retention_policy",
            metadata={**result, "archive_memories": payload.archive_memories},
            request=request,
        )
        return result

    @app.get("/api/governance/legal-holds")
    def list_legal_holds(workspace_id: int, active_only: bool = False, user: dict = Depends(current_user)) -> dict:
        require_workspace_role(user, workspace_id, {"owner", "admin"})
        return {"items": repository.list_legal_holds(workspace_id=workspace_id, active_only=active_only)}

    @app.post("/api/governance/legal-holds", status_code=201)
    def create_legal_hold(payload: LegalHoldCreate, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        require_workspace_role(user, payload.workspace_id, {"owner", "admin"})
        hold = repository.create_legal_hold(
            workspace_id=payload.workspace_id,
            resource_type=payload.resource_type,
            resource_id=payload.resource_id,
            reason=payload.reason,
            expires_at=payload.expires_at.isoformat() if payload.expires_at else None,
            created_by_user_id=user["id"],
        )
        audit(
            "legal_hold.create",
            user_id=user["id"],
            workspace_id=payload.workspace_id,
            resource_type="legal_hold",
            resource_id=hold["id"],
            metadata={"resource_type": payload.resource_type, "resource_id": payload.resource_id},
            request=request,
        )
        return hold

    @app.post("/api/governance/legal-holds/{hold_id}/release")
    def release_legal_hold(hold_id: int, workspace_id: int, payload: LegalHoldRelease, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        require_workspace_role(user, workspace_id, {"owner", "admin"})
        hold = repository.release_legal_hold(workspace_id=workspace_id, hold_id=hold_id, released_by_user_id=user["id"], reason=payload.reason)
        if not hold:
            raise HTTPException(status_code=404, detail="legal hold not found")
        audit(
            "legal_hold.release",
            user_id=user["id"],
            workspace_id=workspace_id,
            resource_type="legal_hold",
            resource_id=hold_id,
            metadata={"resource_type": hold["resource_type"], "resource_id": hold["resource_id"]},
            request=request,
        )
        return hold

    @app.get("/api/governance/compliance-export")
    def compliance_export(workspace_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("export", request, settings.mutation_rate_limit, user)
        require_workspace_role(user, workspace_id, {"owner", "admin"})
        data = repository.export_workspace_compliance(workspace_id=workspace_id, requester_user_id=user["id"])
        audit("compliance.export", user_id=user["id"], workspace_id=workspace_id, resource_type="workspace", resource_id=workspace_id, request=request)
        return data

    @app.get("/api/workspaces/{workspace_id}/export")
    def export_workspace(workspace_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("export", request, settings.mutation_rate_limit, user)
        require_workspace_role(user, workspace_id, {"owner", "admin", "member", "viewer"})
        data = repository.export_user_data(user["id"], workspace_id)
        audit("workspace.export", user_id=user["id"], workspace_id=workspace_id, resource_type="workspace", resource_id=workspace_id, request=request)
        return data

    @app.get("/api/interventions")
    def list_interventions(workspace_id: int | None = None, user: dict = Depends(current_user)) -> dict:
        if workspace_id is not None:
            require_workspace_role(user, workspace_id, {"owner", "admin", "member", "viewer"})
        return {"items": repository.list_interventions_for_user(user["id"], workspace_id)}

    @app.post("/api/interventions", status_code=201)
    def create_intervention(payload: InterventionCreate, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        source = repository.get_task_for_user(payload.source_analysis_task_id, user["id"], include_detail=False)
        if not source:
            raise HTTPException(status_code=404, detail="analysis not found")
        workspace_id, _ = require_workspace_role(user, payload.workspace_id or source.get("workspace_id"), {"owner", "admin", "member"})
        session = repository.create_intervention_session(user["id"], payload.source_analysis_task_id, payload.target_agent_name)
        if not session:
            raise HTTPException(status_code=404, detail="analysis not found")
        audit(
            "intervention.create",
            user_id=user["id"],
            workspace_id=workspace_id,
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
        session = repository.get_intervention_for_user(session_id, user["id"])
        if not session:
            raise HTTPException(status_code=404, detail="intervention not found")
        require_workspace_role(user, session.get("workspace_id"), {"owner", "admin", "member"})
        message = repository.append_intervention_message(session_id, user["id"], payload.content)
        if not message:
            raise HTTPException(status_code=409, detail="intervention is not open")
        audit("intervention.message", user_id=user["id"], workspace_id=session.get("workspace_id"), resource_type="intervention", resource_id=session_id, request=request)
        return message

    @app.post("/api/interventions/{session_id}/pause")
    def pause_intervention(session_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_intervention_for_user(session_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="intervention not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin", "member"})
        if current["status"] == "closed":
            raise HTTPException(status_code=409, detail="intervention is closed")
        session = repository.set_intervention_status(session_id, user["id"], "paused")
        if not session:
            raise HTTPException(status_code=404, detail="intervention not found")
        audit("intervention.pause", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="intervention", resource_id=session_id, request=request)
        return session

    @app.post("/api/interventions/{session_id}/resume")
    def resume_intervention(session_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_intervention_for_user(session_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="intervention not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin", "member"})
        if current["status"] == "closed":
            raise HTTPException(status_code=409, detail="intervention is closed")
        session = repository.set_intervention_status(session_id, user["id"], "open")
        if not session:
            raise HTTPException(status_code=404, detail="intervention not found")
        audit("intervention.resume", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="intervention", resource_id=session_id, request=request)
        return session

    @app.post("/api/interventions/{session_id}/close")
    def close_intervention(session_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_intervention_for_user(session_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="intervention not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin", "member"})
        session = repository.set_intervention_status(session_id, user["id"], "closed")
        if not session:
            raise HTTPException(status_code=404, detail="intervention not found")
        audit("intervention.close", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="intervention", resource_id=session_id, request=request)
        return session

    @app.post("/api/interventions/{session_id}/run", status_code=201)
    def run_intervention(session_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("intervention", request, settings.intervention_rate_limit, user)
        idem_key, cached = get_idempotent_response(request, user, f"intervention.run:{session_id}")
        if cached is not None:
            return cached
        current = repository.get_intervention_for_user(session_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="intervention not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin", "member"})
        enforce_real_runner_budget(user, int(current.get("workspace_id") or repository.get_personal_workspace_id(user["id"])), request)
        output = intervention_service.run_continuation(session_id, user["id"])
        if not output:
            raise HTTPException(status_code=409, detail="intervention is not open")
        audit("intervention.run", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="intervention", resource_id=session_id, request=request)
        store_idempotent_response(idem_key, output)
        return output

    @app.delete("/api/interventions/{session_id}", status_code=204)
    def delete_intervention(session_id: int, request: Request, user: dict = Depends(current_user)) -> Response:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_intervention_for_user(session_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="intervention not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin"})
        if not repository.delete_intervention_for_user(session_id, user["id"]):
            raise HTTPException(status_code=404, detail="intervention not found")
        audit("intervention.delete", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="intervention", resource_id=session_id, request=request)
        return Response(status_code=204)

    @app.get("/api/memories")
    def list_memories(
        request: Request,
        workspace_id: int | None = None,
        ticker: str | None = None,
        agent: str | None = None,
        analysis_date: str | None = None,
        query: str | None = None,
        archived: bool | None = False,
        user: dict = Depends(current_user),
    ) -> dict:
        enforce_rate_limit("memory", request, settings.mutation_rate_limit, user)
        if workspace_id is not None:
            require_workspace_role(user, workspace_id, {"owner", "admin", "member", "viewer"})
        return {
            "items": repository.list_memories_for_user(
                user["id"],
                workspace_id=workspace_id,
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
        current = repository.get_memory_for_user(memory_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="memory not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin", "member"})
        memory = repository.update_memory(memory_id, user["id"], payload)
        if not memory:
            raise HTTPException(status_code=404, detail="memory not found")
        audit("memory.update", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="memory", resource_id=memory_id, request=request)
        return memory

    @app.post("/api/memories/{memory_id}/archive")
    def archive_memory(memory_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_memory_for_user(memory_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="memory not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin", "member"})
        memory = repository.set_memory_archived(memory_id, user["id"], True)
        if not memory:
            raise HTTPException(status_code=404, detail="memory not found")
        audit("memory.archive", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="memory", resource_id=memory_id, request=request)
        return memory

    @app.post("/api/memories/{memory_id}/unarchive")
    def unarchive_memory(memory_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_memory_for_user(memory_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="memory not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin", "member"})
        memory = repository.set_memory_archived(memory_id, user["id"], False)
        if not memory:
            raise HTTPException(status_code=404, detail="memory not found")
        audit("memory.unarchive", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="memory", resource_id=memory_id, request=request)
        return memory

    @app.post("/api/schedules", status_code=201)
    def create_schedule(payload: ScheduledAnalysisCreate, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        workspace_id, _ = require_workspace_role(user, payload.workspace_id, {"owner", "admin", "member"})
        payload = payload.model_copy(update={"workspace_id": workspace_id})
        schedule = scheduler_service.create_schedule(user["id"], payload)
        audit("schedule.create", user_id=user["id"], workspace_id=workspace_id, resource_type="schedule", resource_id=schedule["id"], request=request)
        return schedule

    @app.get("/api/schedules")
    def list_schedules(workspace_id: int | None = None, user: dict = Depends(current_user)) -> dict:
        if workspace_id is not None:
            require_workspace_role(user, workspace_id, {"owner", "admin", "member", "viewer"})
        return {"items": repository.list_schedules_for_user(user["id"], workspace_id)}

    @app.get("/api/schedules/{schedule_id}")
    def get_schedule(schedule_id: int, user: dict = Depends(current_user)) -> dict:
        schedule = repository.get_schedule_for_user(schedule_id, user["id"])
        if not schedule:
            raise HTTPException(status_code=404, detail="schedule not found")
        return schedule

    @app.patch("/api/schedules/{schedule_id}")
    def update_schedule(schedule_id: int, payload: ScheduledAnalysisUpdate, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_schedule_for_user(schedule_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="schedule not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin", "member"})
        schedule = repository.update_schedule(schedule_id, user["id"], payload)
        if not schedule:
            raise HTTPException(status_code=404, detail="schedule not found")
        audit("schedule.update", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="schedule", resource_id=schedule_id, request=request)
        return schedule

    @app.delete("/api/schedules/{schedule_id}", status_code=204)
    def delete_schedule(schedule_id: int, request: Request, user: dict = Depends(current_user)) -> Response:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_schedule_for_user(schedule_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="schedule not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin"})
        if not repository.delete_schedule(schedule_id, user["id"]):
            raise HTTPException(status_code=404, detail="schedule not found")
        audit("schedule.delete", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="schedule", resource_id=schedule_id, request=request)
        return Response(status_code=204)

    @app.post("/api/schedules/{schedule_id}/pause")
    def pause_schedule(schedule_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_schedule_for_user(schedule_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="schedule not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin", "member"})
        schedule = repository.set_schedule_status(schedule_id, user["id"], "paused")
        if not schedule:
            raise HTTPException(status_code=404, detail="schedule not found")
        audit("schedule.pause", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="schedule", resource_id=schedule_id, request=request)
        return schedule

    @app.post("/api/schedules/{schedule_id}/resume")
    def resume_schedule(schedule_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        current = repository.get_schedule_for_user(schedule_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="schedule not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin", "member"})
        schedule = repository.set_schedule_status(schedule_id, user["id"], "active")
        if not schedule:
            raise HTTPException(status_code=404, detail="schedule not found")
        audit("schedule.resume", user_id=user["id"], workspace_id=current.get("workspace_id"), resource_type="schedule", resource_id=schedule_id, request=request)
        return schedule

    @app.post("/api/schedules/{schedule_id}/trigger", status_code=201)
    def trigger_schedule(schedule_id: int, request: Request, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        idem_key, cached = get_idempotent_response(request, user, f"schedule.trigger:{schedule_id}")
        if cached is not None:
            return cached
        current = repository.get_schedule_for_user(schedule_id, user["id"])
        if not current:
            raise HTTPException(status_code=404, detail="schedule not found")
        require_workspace_role(user, current.get("workspace_id"), {"owner", "admin", "member"})
        enforce_real_runner_budget(user, int(current.get("workspace_id") or repository.get_personal_workspace_id(user["id"])), request)
        lock = coordinator.acquire_lock(f"schedule:trigger:{schedule_id}", ttl_seconds=300)
        if lock is None:
            audit(
                "schedule.duplicate_suppressed",
                user_id=user["id"],
                workspace_id=current.get("workspace_id"),
                resource_type="schedule",
                resource_id=schedule_id,
                request=request,
            )
            raise HTTPException(status_code=409, detail="schedule execution already in progress")
        try:
            execution = scheduler_service.execute_schedule(user["id"], schedule_id, run_inline=run_tasks_inline, triggered_by="manual")
            if not execution:
                raise HTTPException(status_code=404, detail="schedule not found")
        finally:
            lock.release()
        audit(
            "schedule.trigger",
            user_id=user["id"],
            workspace_id=current.get("workspace_id"),
            resource_type="schedule",
            resource_id=schedule_id,
            metadata={"execution_id": execution["id"], "analysis_task_id": execution.get("analysis_task_id")},
            request=request,
        )
        store_idempotent_response(idem_key, execution)
        return execution

    @app.post("/api/scheduler/run-due")
    def run_due_schedules(payload: RunDueRequest, request: Request, workspace_id: int | None = None, user: dict = Depends(current_user)) -> dict:
        enforce_rate_limit("mutation", request, settings.mutation_rate_limit, user)
        if workspace_id is not None:
            require_workspace_role(user, workspace_id, {"owner", "admin", "member"})
        now = format_iso_datetime(payload.now) if payload.now else None
        executions = scheduler_service.run_due_for_user(
            user["id"],
            now=now,
            run_inline=run_tasks_inline,
            workspace_id=workspace_id,
            before_execute=lambda schedule: enforce_real_runner_budget(
                user,
                int(schedule.get("workspace_id") or repository.get_personal_workspace_id(user["id"])),
                request,
            ),
            lock_schedule=lambda schedule: coordinator.acquire_lock(f"schedule:due:{schedule['id']}", ttl_seconds=300),
            on_duplicate=lambda schedule: audit(
                "schedule.duplicate_suppressed",
                user_id=user["id"],
                workspace_id=schedule.get("workspace_id"),
                resource_type="schedule",
                resource_id=schedule["id"],
                request=request,
            ),
        )
        audit(
            "schedule.run_due",
            user_id=user["id"],
            workspace_id=workspace_id,
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
                if current["status"] in {"completed", "failed", "cancelled", "paused"}:
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
