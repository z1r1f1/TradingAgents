from __future__ import annotations

from pathlib import Path
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tradingagents.web.main import create_app
from tradingagents.web.settings import WebSettings


def login(client: TestClient, email: str = "cluster@example.com") -> dict[str, str]:
    password = "correct horse battery staple"
    response = client.post("/api/auth/register", json={"email": email, "password": password})
    assert response.status_code == 201
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def analysis_payload(ticker: str = "SPY") -> dict:
    return {
        "ticker": ticker,
        "analysis_date": "2026-05-01",
        "analysts": ["market"],
        "research_depth": 1,
        "llm_provider": "openai",
        "quick_model": "gpt-5.4-mini",
        "deep_model": "gpt-5.5",
        "output_language": "English",
    }


def test_cluster_mode_requires_postgres_and_redis_configuration(tmp_path: Path):
    with pytest.raises(ValueError, match="Postgres"):
        WebSettings(
            database_path=tmp_path / "local.sqlite3",
            runtime_mode="production-cluster",
            postgres_dsn=None,
            redis_url="redis://localhost:6379/0",
            web_env="production",
            auth_secret="strong-production-secret-value",
            allow_registration=False,
            cors_origins=("https://app.example.com",),
        ).validate_for_startup()

    with pytest.raises(ValueError, match="Redis"):
        WebSettings(
            database_path=tmp_path / "local.sqlite3",
            runtime_mode="production-cluster",
            postgres_dsn="postgresql://user:pass@localhost:5432/tradingagents",
            redis_url=None,
            web_env="production",
            auth_secret="strong-production-secret-value",
            allow_registration=False,
            cors_origins=("https://app.example.com",),
        ).validate_for_startup()


def test_cluster_mode_rejects_unreachable_postgres_before_serving(tmp_path: Path):
    from tradingagents.web.coordination import InMemoryCoordinator

    settings = WebSettings(
        database_path=tmp_path / "local.sqlite3",
        runtime_mode="production-cluster",
        postgres_dsn="postgresql://invalid:invalid@127.0.0.1:1/missing",
        redis_url="redis://localhost:6379/0",
        web_env="development",
        auth_secret="test-secret",
    )

    with pytest.raises(ValueError, match="Postgres"):
        create_app(settings=settings, coordinator=InMemoryCoordinator(namespace="test"))


def test_in_memory_coordinator_shares_rate_limits_budget_locks_and_idempotency():
    from tradingagents.web.coordination import InMemoryCoordinator

    coordinator = InMemoryCoordinator(namespace="test")

    assert coordinator.check_rate_limit("auth", "user:1", limit=2, window_seconds=60).allowed is True
    assert coordinator.check_rate_limit("auth", "user:1", limit=2, window_seconds=60).allowed is True
    limited = coordinator.check_rate_limit("auth", "user:1", limit=2, window_seconds=60)
    assert limited.allowed is False
    assert limited.reason == "rate limit exceeded"

    assert coordinator.try_consume_budget(user_id=1, workspace_id=10, user_limit=1, workspace_limit=2).allowed is True
    budget_block = coordinator.try_consume_budget(user_id=1, workspace_id=10, user_limit=1, workspace_limit=2)
    assert budget_block.allowed is False
    assert budget_block.reason == "user budget exceeded"

    lock = coordinator.acquire_lock("schedule:due:7", ttl_seconds=30)
    assert lock is not None
    assert coordinator.acquire_lock("schedule:due:7", ttl_seconds=30) is None
    lock.release()
    assert coordinator.acquire_lock("schedule:due:7", ttl_seconds=30) is not None

    assert coordinator.get_idempotent_response("analysis:create:abc") is None
    coordinator.store_idempotent_response("analysis:create:abc", {"id": 42}, ttl_seconds=60)
    assert coordinator.get_idempotent_response("analysis:create:abc") == {"id": 42}


def test_redis_coordinator_uses_namespaced_shared_primitives():
    from tradingagents.web.coordination import RedisCoordinator

    class FakeRedis:
        def __init__(self):
            self.values: dict[str, str] = {}
            self.expirations: dict[str, int] = {}

        def ping(self):
            return True

        def incr(self, key):
            self.values[key] = str(int(self.values.get(key, "0")) + 1)
            return int(self.values[key])

        def expire(self, key, seconds):
            self.expirations[key] = seconds

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value, nx=False, ex=None):
            if nx and key in self.values:
                return False
            self.values[key] = str(value)
            if ex:
                self.expirations[key] = ex
            return True

        def delete(self, key):
            self.values.pop(key, None)

    fake = FakeRedis()
    coordinator = RedisCoordinator("redis://unused", namespace="phase7", client=fake)

    assert coordinator.check_health()["backend"] == "redis"
    assert coordinator.check_rate_limit("auth", "user:1", limit=1, window_seconds=60).allowed is True
    assert coordinator.check_rate_limit("auth", "user:1", limit=1, window_seconds=60).allowed is False
    assert any(key.startswith("phase7:rate:auth:user:1") for key in fake.values)

    assert coordinator.try_consume_budget(user_id=1, workspace_id=2, user_limit=1, workspace_limit=1).allowed is True
    assert coordinator.try_consume_budget(user_id=1, workspace_id=2, user_limit=1, workspace_limit=1).allowed is False
    assert fake.values["phase7:budget:user:1"] == "1"

    lock = coordinator.acquire_lock("schedule:due:9", ttl_seconds=30)
    assert lock is not None
    assert coordinator.acquire_lock("schedule:due:9", ttl_seconds=30) is None
    lock.release()
    assert coordinator.acquire_lock("schedule:due:9", ttl_seconds=30) is not None

    coordinator.store_idempotent_response("abc", {"id": 3}, ttl_seconds=60)
    assert coordinator.get_idempotent_response("abc") == {"id": 3}


def test_redis_coordinator_reports_unreachable_dependency_clearly():
    from tradingagents.web.coordination import RedisCoordinator

    class BrokenRedis:
        def ping(self):
            raise OSError("connection refused")

    with pytest.raises(ValueError, match="Redis"):
        RedisCoordinator("redis://unused", namespace="phase7", client=BrokenRedis()).check_health()


def test_idempotency_key_replays_analysis_without_duplicate_side_effects(tmp_path: Path):
    from tradingagents.web.coordination import InMemoryCoordinator

    coordinator = InMemoryCoordinator(namespace="test")
    settings = WebSettings(database_path=tmp_path / "web.sqlite3", auth_secret="test-secret", runner_mode="demo")
    client = TestClient(create_app(settings=settings, run_tasks_inline=True, coordinator=coordinator))
    headers = {**login(client), "Idempotency-Key": "same-analysis"}

    first = client.post("/api/analyses", headers=headers, json=analysis_payload("SPY"))
    second = client.post("/api/analyses", headers=headers, json=analysis_payload("SPY"))

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    history = client.get("/api/analyses", headers={k: v for k, v in headers.items() if k != "Idempotency-Key"}).json()
    assert [item["id"] for item in history["items"]] == [first.json()["id"]]
    audit = client.get("/api/governance/audit", headers=headers, params={"event_type": "idempotency.replay"})
    assert audit.json()["items"]


def test_due_schedule_lock_suppresses_duplicate_cluster_execution(tmp_path: Path):
    from tradingagents.web.coordination import InMemoryCoordinator

    coordinator = InMemoryCoordinator(namespace="test")
    settings = WebSettings(database_path=tmp_path / "web.sqlite3", auth_secret="test-secret", runner_mode="demo")
    client = TestClient(create_app(settings=settings, run_tasks_inline=True, coordinator=coordinator))
    headers = login(client)
    schedule = client.post(
        "/api/schedules",
        headers=headers,
        json={
            **analysis_payload("SPY"),
            "name": "Due once",
            "start_at": "2026-05-01T09:30:00+00:00",
            "interval": "daily",
        },
    ).json()

    held = coordinator.acquire_lock(f"schedule:due:{schedule['id']}", ttl_seconds=30)
    assert held is not None
    result = client.post("/api/scheduler/run-due", headers=headers, json={"now": "2026-05-02T10:00:00+00:00"})

    assert result.status_code == 200
    assert result.json()["executed"] == 0
    audit = client.get("/api/governance/audit", headers=headers, params={"event_type": "schedule.duplicate_suppressed"})
    assert audit.json()["items"][0]["resource_id"] == str(schedule["id"])


def test_cluster_runtime_health_reports_mode_without_secrets(tmp_path: Path):
    from tradingagents.web.coordination import InMemoryCoordinator

    settings = WebSettings(
        database_path=tmp_path / "web.sqlite3",
        runtime_mode="local",
        postgres_dsn="postgresql://user:secret@db.example.com:5432/tradingagents",
        redis_url="redis://:secret@redis.example.com:6379/0",
        auth_secret="test-secret",
    )
    client = TestClient(create_app(settings=settings, run_tasks_inline=True, coordinator=InMemoryCoordinator(namespace="test")))

    health = client.get("/api/health").json()

    assert health["runtime_mode"] == "local"
    assert health["storage_backend"] == "sqlite"
    assert health["coordination_backend"] == "memory"
    assert "secret" not in str(health)


def test_postgres_schema_manager_declares_all_phase_tables():
    from tradingagents.web.postgres import PostgresSchemaManager

    assert {
        "users",
        "sessions",
        "workspaces",
        "workspace_members",
        "analysis_tasks",
        "agent_event_logs",
        "schedules",
        "agent_memories",
        "intervention_sessions",
        "audit_logs",
        "schema_migrations",
    } <= set(PostgresSchemaManager.required_tables())


def test_postgres_and_redis_integration_when_services_are_available():
    postgres_dsn = os.getenv("TRADINGAGENTS_TEST_POSTGRES_DSN")
    redis_url = os.getenv("TRADINGAGENTS_TEST_REDIS_URL")
    if not postgres_dsn or not redis_url:
        pytest.skip("TRADINGAGENTS_TEST_POSTGRES_DSN and TRADINGAGENTS_TEST_REDIS_URL are not configured")

    settings = WebSettings(
        runtime_mode="production-cluster",
        postgres_dsn=postgres_dsn,
        redis_url=redis_url,
        web_env="development",
        auth_secret="test-secret",
        allow_registration=True,
    )
    client_one = TestClient(create_app(settings=settings, run_tasks_inline=True))
    client_two = TestClient(create_app(settings=settings, run_tasks_inline=True))

    email = f"cluster-shared-{uuid.uuid4().hex}@example.com"
    headers = login(client_one, email)
    task = client_one.post("/api/analyses", headers=headers, json=analysis_payload("SPY"))
    assert task.status_code == 201

    login_two = client_two.post(
        "/api/auth/login",
        json={"email": email, "password": "correct horse battery staple"},
    )
    assert login_two.status_code == 200
    headers_two = {"Authorization": f"Bearer {login_two.json()['access_token']}"}
    history = client_two.get("/api/analyses", headers=headers_two)
    assert history.status_code == 200
    assert any(item["id"] == task.json()["id"] for item in history.json()["items"])

    member_email = f"cluster-member-{uuid.uuid4().hex}@example.com"
    member_headers = login(client_two, member_email)
    workspace = client_one.post("/api/workspaces", headers=headers, json={"name": "Cluster RBAC"}).json()
    member = client_one.post(
        f"/api/workspaces/{workspace['id']}/members",
        headers=headers,
        json={"email": member_email, "role": "viewer"},
    )
    assert member.status_code == 201
    denied = client_two.post("/api/analyses", headers=member_headers, json={**analysis_payload("MSFT"), "workspace_id": workspace["id"]})
    assert denied.status_code == 403
    promoted = client_one.patch(
        f"/api/workspaces/{workspace['id']}/members/{member.json()['user_id']}",
        headers=headers,
        json={"role": "member"},
    )
    assert promoted.status_code == 200
    shared_task = client_two.post("/api/analyses", headers=member_headers, json={**analysis_payload("MSFT"), "workspace_id": workspace["id"]})
    assert shared_task.status_code == 201
    assert client_one.get(f"/api/analyses/{shared_task.json()['id']}", headers=headers).status_code == 200
