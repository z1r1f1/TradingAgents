from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from tradingagents.web.main import create_app
from tradingagents.web.settings import WebSettings


def make_client(tmp_path: Path) -> tuple[TestClient, Path]:
    db_path = tmp_path / "web.sqlite3"
    settings = WebSettings(
        database_path=db_path,
        auth_secret="test-secret",
        runner_mode="demo",
        allow_registration=True,
    )
    return TestClient(create_app(settings=settings, run_tasks_inline=True)), db_path


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": "ada@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 201
    response = client.post(
        "/api/auth/login",
        json={"email": "ada@example.com", "password": "correct horse battery staple"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_protected_routes_require_authentication(tmp_path: Path):
    client, _ = make_client(tmp_path)

    assert client.get("/health").status_code == 200
    assert client.get("/api/analyses").status_code in {401, 403}
    assert client.post("/api/analyses", json={}).status_code in {401, 403}


def test_authenticated_user_can_create_analysis_and_persist_results(tmp_path: Path):
    client, db_path = make_client(tmp_path)
    headers = login(client)

    response = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "SPY",
            "analysis_date": "2026-05-01",
            "analysts": ["market", "news"],
            "research_depth": 2,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    )

    assert response.status_code == 201
    task = response.json()
    assert task["status"] == "completed"
    task_id = task["id"]

    detail = client.get(f"/api/analyses/{task_id}", headers=headers).json()
    assert detail["parameters"]["ticker"] == "SPY"
    assert detail["final_decision"]["decision"] in {"BUY", "HOLD", "SELL"}
    assert {section["section_name"] for section in detail["report_sections"]} >= {
        "market_report",
        "news_report",
        "final_trade_decision",
    }
    assert any(event["agent"] == "Market Analyst" for event in detail["events"])

    with sqlite3.connect(db_path) as conn:
        task_count = conn.execute("select count(*) from analysis_tasks").fetchone()[0]
        params_count = conn.execute("select count(*) from task_parameters").fetchone()[0]
        events_count = conn.execute("select count(*) from agent_event_logs").fetchone()[0]
        final_count = conn.execute("select count(*) from final_decisions").fetchone()[0]
        sections_count = conn.execute("select count(*) from report_sections").fetchone()[0]

    assert task_count == 1
    assert params_count == 1
    assert events_count >= 4
    assert final_count == 1
    assert sections_count >= 3


def test_history_detail_rerun_and_sse_events(tmp_path: Path):
    client, _ = make_client(tmp_path)
    headers = login(client)
    create = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "MSFT",
            "analysis_date": "2026-05-01",
            "analysts": ["fundamentals"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    ).json()

    history = client.get("/api/analyses", headers=headers).json()
    assert [item["id"] for item in history["items"]] == [create["id"]]

    events_response = client.get(f"/api/analyses/{create['id']}/events", headers=headers)
    assert events_response.status_code == 200
    assert "text/event-stream" in events_response.headers["content-type"]
    assert "event: task_event" in events_response.text
    assert "Portfolio Manager" in events_response.text

    rerun = client.post(
        f"/api/analyses/{create['id']}/rerun",
        headers=headers,
        json={"ticker": "AAPL", "research_depth": 2},
    )
    assert rerun.status_code == 201
    rerun_task = rerun.json()
    assert rerun_task["id"] != create["id"]

    rerun_detail = client.get(f"/api/analyses/{rerun_task['id']}", headers=headers).json()
    assert rerun_detail["parameters"]["ticker"] == "AAPL"
    assert rerun_detail["parameters"]["analysts"] == ["fundamentals"]
    assert rerun_detail["parameters"]["research_depth"] == 2


def test_real_graph_runner_emits_progressive_events_from_stream(monkeypatch):
    """Real runner seam must stream graph chunks instead of waiting for propagate()."""

    from tradingagents.web.runner import TradingAgentsGraphRunner
    from tradingagents.web.schemas import AnalysisCreate
    import tradingagents.graph.trading_graph as trading_graph_module

    emitted: list[tuple[str, str, str]] = []

    class FakeMemoryLog:
        def get_past_context(self, ticker):
            assert ticker == "SPY"
            return "past context"

    class FakePropagator:
        def create_initial_state(self, ticker, analysis_date, past_context=None):
            assert (ticker, analysis_date, past_context) == ("SPY", "2026-05-01", "past context\n\nselected memory context")
            return {"ticker": ticker}

        def get_graph_args(self):
            return {}

    class FakeCompiledGraph:
        def stream(self, initial_state, **kwargs):
            assert initial_state == {"ticker": "SPY"}
            yield {
                "market_report": "market report while running",
                "messages": [],
            }
            yield {
                "investment_plan": "research manager plan while running",
                "messages": [],
            }
            yield {
                "market_report": "market report final",
                "investment_plan": "research manager plan final",
                "trader_investment_plan": "trader plan final",
                "final_trade_decision": "BUY SPY because momentum improved",
                "messages": [],
            }

    class FakeTradingAgentsGraph:
        def __init__(self, selected_analysts, config, debug=False):
            assert selected_analysts == ["market"]
            assert config["max_debate_rounds"] == 1
            self.memory_log = FakeMemoryLog()
            self.propagator = FakePropagator()
            self.graph = FakeCompiledGraph()
            self.curr_state = None

        def propagate(self, *args, **kwargs):  # pragma: no cover - should not be reached
            raise AssertionError("runner must stream progressively instead of waiting for propagate")

        def process_signal(self, raw_signal):
            assert raw_signal == "BUY SPY because momentum improved"
            return "BUY"

    monkeypatch.setattr(trading_graph_module, "TradingAgentsGraph", FakeTradingAgentsGraph)

    params = AnalysisCreate(
        ticker="SPY",
        analysis_date="2026-05-01",
        analysts=["market"],
        research_depth=1,
        llm_provider="openai",
        quick_model="gpt-5.4-mini",
        deep_model="gpt-5.5",
        output_language="English",
        memory_context="selected memory context",
    )

    result = TradingAgentsGraphRunner().run(
        params,
        lambda event: emitted.append((event.agent, event.event_type, event.message)),
    )

    assert ("Market Analyst", "report.section", "market report while running") in emitted
    assert ("Research Manager", "report.section", "research manager plan while running") in emitted
    assert emitted.index(("Market Analyst", "report.section", "market report while running")) < emitted.index(
        ("Portfolio Manager", "agent.completed", "BUY SPY because momentum improved")
    )
    assert result.final_decision["decision"] == "BUY"
    assert result.report_sections["market_report"] == "market report final"


def test_schedule_crud_manual_trigger_and_owner_isolation(tmp_path: Path):
    client, db_path = make_client(tmp_path)
    headers = login(client)
    other_register = client.post(
        "/api/auth/register",
        json={"email": "grace@example.com", "password": "correct horse battery staple"},
    )
    assert other_register.status_code == 201
    other_login = client.post(
        "/api/auth/login",
        json={"email": "grace@example.com", "password": "correct horse battery staple"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    unauth = client.get("/api/schedules")
    assert unauth.status_code in {401, 403}

    create = client.post(
        "/api/schedules",
        headers=headers,
        json={
            "name": "Weekly SPY",
            "ticker": "SPY",
            "start_at": "2026-05-01T09:30:00+00:00",
            "interval": "weekly",
            "analysts": ["market", "news"],
            "research_depth": 2,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    )
    assert create.status_code == 201
    schedule = create.json()
    schedule_id = schedule["id"]
    assert schedule["status"] == "active"
    assert schedule["next_run_at"] == "2026-05-01T09:30:00+00:00"

    listed = client.get("/api/schedules", headers=headers).json()
    assert [item["id"] for item in listed["items"]] == [schedule_id]
    assert client.get(f"/api/schedules/{schedule_id}", headers=other_headers).status_code == 404

    paused = client.post(f"/api/schedules/{schedule_id}/pause", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    resumed = client.post(f"/api/schedules/{schedule_id}/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"

    updated = client.patch(
        f"/api/schedules/{schedule_id}",
        headers=headers,
        json={"ticker": "AAPL", "research_depth": 3, "interval": "monthly"},
    )
    assert updated.status_code == 200
    assert updated.json()["ticker"] == "AAPL"
    assert updated.json()["research_depth"] == 3
    assert updated.json()["interval"] == "monthly"

    trigger = client.post(f"/api/schedules/{schedule_id}/trigger", headers=headers)
    assert trigger.status_code == 201
    execution = trigger.json()
    assert execution["schedule_id"] == schedule_id
    assert execution["status"] == "completed"
    assert execution["analysis_task_id"] is not None

    task_detail = client.get(f"/api/analyses/{execution['analysis_task_id']}", headers=headers).json()
    assert task_detail["parameters"]["ticker"] == "AAPL"
    assert task_detail["parameters"]["research_depth"] == 3

    with sqlite3.connect(db_path) as conn:
        schedule_count = conn.execute("select count(*) from schedules").fetchone()[0]
        execution_count = conn.execute("select count(*) from schedule_executions").fetchone()[0]
        task_count = conn.execute("select count(*) from analysis_tasks").fetchone()[0]

    assert schedule_count == 1
    assert execution_count == 1
    assert task_count == 1

    deleted = client.delete(f"/api/schedules/{schedule_id}", headers=headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/schedules/{schedule_id}", headers=headers).status_code == 404


def test_due_schedule_calculation_and_explicit_runner_entrypoint(tmp_path: Path):
    from tradingagents.web.scheduler import compute_next_run_at

    assert compute_next_run_at("2026-05-01T09:30:00+00:00", "daily", after="2026-05-01T09:30:00+00:00") == "2026-05-02T09:30:00+00:00"
    assert compute_next_run_at("2026-05-01T09:30:00+00:00", "weekly", after="2026-05-01T09:30:00+00:00") == "2026-05-08T09:30:00+00:00"
    assert compute_next_run_at("2026-01-31T09:30:00+00:00", "monthly", after="2026-01-31T09:30:00+00:00") == "2026-02-28T09:30:00+00:00"

    client, db_path = make_client(tmp_path)
    headers = login(client)
    create = client.post(
        "/api/schedules",
        headers=headers,
        json={
            "name": "Daily Due",
            "ticker": "SPY",
            "start_at": "2026-05-01T09:30:00+00:00",
            "interval": "daily",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    ).json()

    run_due = client.post("/api/scheduler/run-due", headers=headers, json={"now": "2026-05-02T10:00:00+00:00"})
    assert run_due.status_code == 200
    result = run_due.json()
    assert result["executed"] == 1
    assert result["executions"][0]["schedule_id"] == create["id"]
    assert result["executions"][0]["status"] == "completed"

    refreshed = client.get(f"/api/schedules/{create['id']}", headers=headers).json()
    assert refreshed["last_run_at"] is not None
    assert refreshed["next_run_at"] == "2026-05-03T09:30:00+00:00"

    with sqlite3.connect(db_path) as conn:
        execution = conn.execute(
            "select schedule_id, analysis_task_id, status, started_at, completed_at, error from schedule_executions"
        ).fetchone()

    assert execution[0] == create["id"]
    assert execution[1] is not None
    assert execution[2] == "completed"
    assert execution[3] is not None
    assert execution[4] is not None
    assert execution[5] is None


def test_completed_analysis_extracts_owned_searchable_agent_memories(tmp_path: Path):
    client, db_path = make_client(tmp_path)
    headers = login(client)
    other_register = client.post(
        "/api/auth/register",
        json={"email": "memory-other@example.com", "password": "correct horse battery staple"},
    )
    assert other_register.status_code == 201
    other_login = client.post(
        "/api/auth/login",
        json={"email": "memory-other@example.com", "password": "correct horse battery staple"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    assert client.get("/api/memories").status_code in {401, 403}

    created = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "SPY",
            "analysis_date": "2026-05-01",
            "analysts": ["market", "news"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    ).json()

    memories = client.get("/api/memories", headers=headers).json()["items"]
    agents = {memory["agent_name"] for memory in memories}
    assert {"Market Analyst", "News Analyst", "Research Manager", "Trader", "Portfolio Manager"} <= agents
    assert all(memory["ticker"] == "SPY" for memory in memories)
    assert all(memory["source_analysis_task_id"] == created["id"] for memory in memories)

    market = client.get("/api/memories", headers=headers, params={"ticker": "SPY", "agent": "Market Analyst", "query": "Demo"}).json()["items"]
    assert len(market) == 1
    memory_id = market[0]["id"]
    detail = client.get(f"/api/memories/{memory_id}", headers=headers).json()
    assert detail["content"].startswith("Demo Market Analyst report")
    assert client.get(f"/api/memories/{memory_id}", headers=other_headers).status_code == 404

    archived = client.post(f"/api/memories/{memory_id}/archive", headers=headers)
    assert archived.status_code == 200
    assert archived.json()["archived"] is True
    assert client.get("/api/memories", headers=headers, params={"archived": "false"}).json()["items"]
    archived_only = client.get("/api/memories", headers=headers, params={"archived": "true"}).json()["items"]
    assert [item["id"] for item in archived_only] == [memory_id]
    unarchived = client.post(f"/api/memories/{memory_id}/unarchive", headers=headers)
    assert unarchived.status_code == 200
    assert unarchived.json()["archived"] is False

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select count(*) from agent_memories").fetchone()[0] >= 5


def test_selected_memories_attach_to_manual_analysis_and_context_is_bounded(tmp_path: Path):
    from tradingagents.web.schemas import RunnerResult

    client, db_path = make_client(tmp_path)
    headers = login(client)
    first = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "SPY",
            "analysis_date": "2026-05-01",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    ).json()
    memory_id = client.get("/api/memories", headers=headers, params={"agent": "Market Analyst"}).json()["items"][0]["id"]

    captured_contexts: list[str | None] = []

    class CapturingRunner:
        def run(self, params, emit):
            captured_contexts.append(params.memory_context)
            return RunnerResult(
                report_sections={"market_report": "second market", "final_trade_decision": "HOLD with memory"},
                final_decision={"decision": "HOLD", "rationale": "used memory", "raw_decision": "HOLD with memory"},
            )

    client.app.state.service.runner = CapturingRunner()
    second = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "AAPL",
            "analysis_date": "2026-05-02",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
            "memory_ids": [memory_id],
        },
    ).json()

    detail = client.get(f"/api/analyses/{second['id']}", headers=headers).json()
    assert [memory["id"] for memory in detail["attached_memories"]] == [memory_id]
    assert captured_contexts and "Market Analyst" in captured_contexts[0]
    assert "Demo Market Analyst report" in captured_contexts[0]
    assert len(captured_contexts[0]) <= 4000

    with sqlite3.connect(db_path) as conn:
        attachment = conn.execute("select analysis_task_id, memory_id from analysis_memory_attachments").fetchone()
    assert attachment == (second["id"], memory_id)
    assert first["id"] != second["id"]


def test_schedule_trigger_attaches_configured_memories(tmp_path: Path):
    client, _ = make_client(tmp_path)
    headers = login(client)
    client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "SPY",
            "analysis_date": "2026-05-01",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    )
    memory_id = client.get("/api/memories", headers=headers, params={"agent": "Market Analyst"}).json()["items"][0]["id"]

    schedule = client.post(
        "/api/schedules",
        headers=headers,
        json={
            "name": "Memory schedule",
            "ticker": "AAPL",
            "start_at": "2026-05-01T09:30:00+00:00",
            "interval": "weekly",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
            "memory_ids": [memory_id],
        },
    ).json()
    assert schedule["memory_ids"] == [memory_id]

    execution = client.post(f"/api/schedules/{schedule['id']}/trigger", headers=headers).json()
    detail = client.get(f"/api/analyses/{execution['analysis_task_id']}", headers=headers).json()
    assert [memory["id"] for memory in detail["attached_memories"]] == [memory_id]


def test_intervention_lifecycle_messages_continuation_and_immutability(tmp_path: Path):
    client, db_path = make_client(tmp_path)
    headers = login(client)
    other_register = client.post(
        "/api/auth/register",
        json={"email": "hitl-other@example.com", "password": "correct horse battery staple"},
    )
    assert other_register.status_code == 201
    other_login = client.post(
        "/api/auth/login",
        json={"email": "hitl-other@example.com", "password": "correct horse battery staple"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    assert client.get("/api/interventions").status_code in {401, 403}

    analysis = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "SPY",
            "analysis_date": "2026-05-01",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    ).json()
    original_detail = client.get(f"/api/analyses/{analysis['id']}", headers=headers).json()
    original_decision = original_detail["final_decision"]
    original_sections = list(original_detail["report_sections"])

    created = client.post(
        "/api/interventions",
        headers=headers,
        json={"source_analysis_task_id": analysis["id"], "target_agent_name": "Market Analyst"},
    )
    assert created.status_code == 201
    session = created.json()
    session_id = session["id"]
    assert session["status"] == "open"
    assert session["target_agent_name"] == "Market Analyst"
    assert client.get(f"/api/interventions/{session_id}", headers=other_headers).status_code == 404

    message = client.post(
        f"/api/interventions/{session_id}/messages",
        headers=headers,
        json={"content": "Re-check demand using the latest channel checks."},
    )
    assert message.status_code == 201
    assert message.json()["sequence"] == 1
    assert message.json()["author"] == "user"

    paused = client.post(f"/api/interventions/{session_id}/pause", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    resumed = client.post(f"/api/interventions/{session_id}/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "open"

    continuation = client.post(f"/api/interventions/{session_id}/run", headers=headers)
    assert continuation.status_code == 201
    output = continuation.json()
    assert output["session_id"] == session_id
    assert output["target_agent_name"] == "Market Analyst"
    assert "Re-check demand" in output["content"]

    detail = client.get(f"/api/interventions/{session_id}", headers=headers).json()
    assert detail["messages"][0]["content"].startswith("Re-check demand")
    assert detail["events"][0]["event_type"] == "continuation.started"
    assert detail["outputs"][0]["content"] == output["content"]

    linked_analysis = client.get(f"/api/analyses/{analysis['id']}", headers=headers).json()
    assert [item["id"] for item in linked_analysis["intervention_sessions"]] == [session_id]
    assert linked_analysis["final_decision"] == original_decision
    assert linked_analysis["report_sections"] == original_sections

    closed = client.post(f"/api/interventions/{session_id}/close", headers=headers)
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    rejected_message = client.post(
        f"/api/interventions/{session_id}/messages",
        headers=headers,
        json={"content": "should not be accepted after close"},
    )
    assert rejected_message.status_code == 409
    assert client.post(f"/api/interventions/{session_id}/resume", headers=headers).status_code == 409

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select count(*) from intervention_sessions").fetchone()[0] == 1
        assert conn.execute("select count(*) from intervention_messages").fetchone()[0] == 1
        assert conn.execute("select count(*) from intervention_events").fetchone()[0] >= 2
        assert conn.execute("select count(*) from intervention_outputs").fetchone()[0] == 1


def test_intervention_continuation_uses_attached_memories_without_cross_user_leak(tmp_path: Path):
    client, _ = make_client(tmp_path)
    headers = login(client)
    first = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "SPY",
            "analysis_date": "2026-05-01",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    ).json()
    memory_id = client.get("/api/memories", headers=headers, params={"agent": "Market Analyst"}).json()["items"][0]["id"]
    second = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "AAPL",
            "analysis_date": "2026-05-02",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
            "memory_ids": [memory_id],
        },
    ).json()
    session = client.post(
        "/api/interventions",
        headers=headers,
        json={"source_analysis_task_id": second["id"], "target_agent_name": "Market Analyst"},
    ).json()
    client.post(
        f"/api/interventions/{session['id']}/messages",
        headers=headers,
        json={"content": "Use attached memory only."},
    )
    output = client.post(f"/api/interventions/{session['id']}/run", headers=headers).json()
    assert "Attached memories: 1" in output["content"]
    assert "Use attached memory only" in output["content"]
    assert first["id"] != second["id"]
