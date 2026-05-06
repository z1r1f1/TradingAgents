from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tradingagents.web.main import create_app
from tradingagents.web.settings import WebSettings


def make_client(tmp_path: Path, **settings_overrides) -> tuple[TestClient, Path]:
    db_path = tmp_path / "web.sqlite3"
    settings = WebSettings(
        database_path=db_path,
        auth_secret="test-secret",
        runner_mode="demo",
        allow_registration=True,
        **settings_overrides,
    )
    return TestClient(create_app(settings=settings, run_tasks_inline=True)), db_path


def register_login(client: TestClient, email: str = "owner@example.com") -> dict[str, str]:
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


def test_oidc_startup_validation_requires_complete_provider_settings(tmp_path: Path):
    with pytest.raises(ValueError, match="OIDC"):
        WebSettings(
            database_path=tmp_path / "web.sqlite3",
            web_env="production",
            auth_secret="strong-production-secret-value",
            allow_registration=False,
            cors_origins=("https://app.example.com",),
            oidc_enabled=True,
            oidc_issuer_url="https://idp.example.com",
            oidc_client_id="tradingagents",
            oidc_client_secret=None,
            oidc_redirect_uri="https://app.example.com/auth/oidc/callback",
        ).validate_for_startup()


def test_mocked_oidc_login_provisions_user_maps_group_and_audits_without_tokens(tmp_path: Path, monkeypatch):
    client, db_path = make_client(
        tmp_path,
        oidc_enabled=True,
        oidc_issuer_url="https://idp.example.com",
        oidc_client_id="tradingagents",
        oidc_client_secret="super-secret-client-value",
        oidc_redirect_uri="http://localhost:5173/auth/oidc/callback",
        oidc_group_role_mapping_json='{"traders":{"workspace_id":1,"role":"member"}}',
    )
    owner_headers = register_login(client)
    workspace = client.post("/api/workspaces", headers=owner_headers, json={"name": "Desk"}).json()
    assert workspace["id"] == 2  # personal workspace is created first, shared workspace second

    class FakeResponse:
        def __init__(self, payload: dict):
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    calls: list[tuple[str, str, dict | None]] = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(("GET", url, headers))
        if url.endswith("/.well-known/openid-configuration"):
            return FakeResponse({"token_endpoint": "https://idp.example.com/token", "userinfo_endpoint": "https://idp.example.com/userinfo"})
        assert headers == {"Authorization": "Bearer oidc-access-token"}
        return FakeResponse({"sub": "idp-subject-1", "email": "ADA@Example.COM", "groups": ["traders"]})

    def fake_post(url, data=None, timeout=None):
        calls.append(("POST", url, data))
        assert data["client_secret"] == "super-secret-client-value"
        return FakeResponse({"access_token": "oidc-access-token", "id_token": "secret-id-token"})

    monkeypatch.setattr("tradingagents.web.main.requests.get", fake_get)
    monkeypatch.setattr("tradingagents.web.main.requests.post", fake_post)

    response = client.post(
        "/api/auth/oidc/callback",
        json={"code": "mock-code", "redirect_uri": "http://localhost:5173/auth/oidc/callback"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "ada@example.com"

    user_headers = {"Authorization": f"Bearer {body['access_token']}"}
    mapped = client.get("/api/workspaces", headers=user_headers).json()["items"]
    assert any(item["id"] == 1 and item["role"] == "member" for item in mapped)

    status = client.get("/api/identity/status", headers=owner_headers).json()
    assert status["oidc_enabled"] is True
    assert status["issuer_url"] == "https://idp.example.com"
    assert "client_secret" not in str(status)

    users = client.get("/api/identity/users", headers=owner_headers, params={"workspace_id": 1}).json()["items"]
    assert users[0]["issuer"] == "https://idp.example.com"
    assert users[0]["subject"] == "idp-subject-1"
    assert users[0]["email"] == "ada@example.com"
    assert users[0]["groups"] == ["traders"]

    with sqlite3.connect(db_path) as conn:
        audit_payloads = [row[0] for row in conn.execute("select metadata_json from audit_logs where event_type like 'auth.oidc.%'")]
    serialized = "\n".join(audit_payloads)
    assert "oidc-access-token" not in serialized
    assert "secret-id-token" not in serialized
    assert "super-secret-client-value" not in serialized
    assert any(call[0] == "POST" and call[1] == "https://idp.example.com/token" for call in calls)


def test_retention_preview_and_apply_are_workspace_scoped_and_preserve_ledgers_by_default(tmp_path: Path):
    client, db_path = make_client(tmp_path)
    owner_headers = register_login(client)
    other_headers = register_login(client, "other@example.com")
    owner_workspace = client.get("/api/workspaces", headers=owner_headers).json()["items"][0]
    other_workspace = client.get("/api/workspaces", headers=other_headers).json()["items"][0]

    owner_task = client.post("/api/analyses", headers=owner_headers, json={**analysis_payload("SPY"), "workspace_id": owner_workspace["id"]}).json()
    other_task = client.post("/api/analyses", headers=other_headers, json={**analysis_payload("MSFT"), "workspace_id": other_workspace["id"]}).json()
    old = "2026-01-01T00:00:00+00:00"
    with sqlite3.connect(db_path) as conn:
        conn.execute("update analysis_tasks set created_at = ?, updated_at = ?", (old, old))
        conn.execute("update agent_memories set created_at = ?", (old,))
        conn.commit()

    preview = client.post(
        "/api/governance/retention/preview",
        headers=owner_headers,
        json={"workspace_id": owner_workspace["id"], "resource_type": "analyses", "cutoff_before": "2026-02-01T00:00:00+00:00"},
    )
    assert preview.status_code == 200
    assert preview.json()["matched_count"] == 1

    apply = client.post(
        "/api/governance/retention/apply",
        headers=owner_headers,
        json={"workspace_id": owner_workspace["id"], "resource_type": "analyses", "cutoff_before": "2026-02-01T00:00:00+00:00"},
    )
    assert apply.status_code == 200
    assert apply.json()["affected_count"] == 1

    assert client.get(f"/api/analyses/{owner_task['id']}", headers=owner_headers).status_code == 404
    assert client.get(f"/api/analyses/{other_task['id']}", headers=other_headers).status_code == 200

    ledger_preview = client.post(
        "/api/governance/retention/preview",
        headers=owner_headers,
        json={"workspace_id": owner_workspace["id"], "resource_type": "usage_ledger", "cutoff_before": "2027-01-01T00:00:00+00:00"},
    )
    assert ledger_preview.status_code == 400
    assert "explicit" in ledger_preview.text

    audit = client.get("/api/governance/audit", headers=owner_headers, params={"event_type": "retention.apply"}).json()["items"]
    assert audit[0]["workspace_id"] == owner_workspace["id"]
    assert audit[0]["metadata"]["resource_type"] == "analyses"
