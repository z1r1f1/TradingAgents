from __future__ import annotations

from datetime import date
import sqlite3
from pathlib import Path
import queue
import threading
import time

import pytest
from fastapi.testclient import TestClient

from tradingagents.web import main as web_main
from tradingagents.web.main import create_app
from tradingagents.web.maintenance import (
    apply_sqlite_to_postgres_migration,
    backup_sqlite_database,
    plan_sqlite_to_postgres_migration,
    validate_sqlite_to_postgres_migration,
)
from tradingagents.web.coordination import InMemoryCoordinator
from tradingagents.web.database import WebRepository
from tradingagents.web.schemas import AnalysisCreate, EventPayload, RunnerResult, ScheduledAnalysisCreate
from tradingagents.web.scheduler import SchedulerService
from tradingagents.web.service import AnalysisService
from tradingagents.web.runner import DemoAnalysisRunner, TradingAgentsGraphRunner
from tradingagents.web.settings import WebSettings
from tradingagents.web.usage import reconcile_usage_ledger


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


def test_stock_search_normalizes_eastmoney_a_share_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, _ = make_client(tmp_path)
    headers = login(client)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "QuotationCodeTable": {
                    "Data": [
                        {
                            "Code": "603386",
                            "Name": "骏亚科技",
                            "PinYin": "JYKJ",
                            "MktNum": "1",
                            "SecurityTypeName": "沪A",
                            "Classify": "AStock",
                        },
                        {
                            "Code": "000767",
                            "Name": "晋控电力",
                            "PinYin": "JKDL",
                            "MktNum": "0",
                            "SecurityTypeName": "深A",
                            "Classify": "AStock",
                        },
                    ]
                }
            }

    def fake_get(url: str, **kwargs):
        assert url == "https://searchapi.eastmoney.com/api/suggest/get"
        assert kwargs["params"]["input"] == "骏亚"
        assert kwargs["params"]["type"] == "14"
        return FakeResponse()

    monkeypatch.setattr(web_main.requests, "get", fake_get)

    response = client.get("/api/stock-search", headers=headers, params={"query": "骏亚"})

    assert response.status_code == 200
    assert response.json()["items"] == [
        {"code": "603386", "name": "骏亚科技", "ticker": "603386.SS", "market": "沪A", "pinyin": "JYKJ"},
        {"code": "000767", "name": "晋控电力", "ticker": "000767.SZ", "market": "深A", "pinyin": "JKDL"},
    ]


def test_stock_search_is_public_read_only_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, _ = make_client(tmp_path)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "QuotationCodeTable": {
                    "Data": [
                        {
                            "Code": "603386",
                            "Name": "骏亚科技",
                            "PinYin": "JYKJ",
                            "MktNum": "1",
                            "SecurityTypeName": "沪A",
                            "Classify": "AStock",
                        }
                    ]
                }
            }

    monkeypatch.setattr(web_main.requests, "get", lambda *args, **kwargs: FakeResponse())

    response = client.get("/api/stock-search", params={"query": "骏亚"})

    assert response.status_code == 200
    assert response.json()["items"][0]["ticker"] == "603386.SS"


def test_analysis_preserves_optional_stock_name_for_history(tmp_path: Path):
    client, _ = make_client(tmp_path)
    headers = login(client)

    response = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "603386.SS",
            "ticker_name": "骏亚科技",
            "analysis_date": "2026-05-01",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "中文",
        },
    )

    assert response.status_code == 201
    task = response.json()
    assert task["ticker_name"] == "骏亚科技"
    assert task["parameters"]["ticker_name"] == "骏亚科技"

    history = client.get("/api/analyses", headers=headers).json()["items"]
    assert history[0]["ticker_name"] == "骏亚科技"
    assert history[0]["parameters"]["ticker_name"] == "骏亚科技"


def test_analysis_service_queue_runs_one_stock_at_a_time(tmp_path: Path):
    class BlockingRunner:
        def __init__(self) -> None:
            self.started: queue.Queue[str] = queue.Queue()
            self.releases: dict[str, threading.Event] = {}

        def run(self, params: AnalysisCreate, emit):
            self.releases.setdefault(params.ticker, threading.Event())
            emit(EventPayload(agent="System", event_type="task.started", message=f"start {params.ticker}"))
            self.started.put(params.ticker)
            assert self.releases[params.ticker].wait(timeout=5), f"timed out waiting to release {params.ticker}"
            emit(EventPayload(agent="System", event_type="task.completed", message=f"done {params.ticker}"))
            return RunnerResult(
                report_sections={"final_trade_decision": f"HOLD {params.ticker}"},
                final_decision={"decision": "HOLD", "confidence": None, "rationale": f"HOLD {params.ticker}", "raw_decision": f"HOLD {params.ticker}"},
            )

    repo = WebRepository(tmp_path / "queue.sqlite3")
    user = repo.create_user("queue@example.com", "correct horse battery staple")
    runner = BlockingRunner()
    service = AnalysisService(repo, runner)
    params_a = AnalysisCreate(
        ticker="AAPL",
        analysis_date="2026-05-01",
        analysts=["market"],
        research_depth=1,
        llm_provider="openai",
        quick_model="gpt-5.4-mini",
        deep_model="gpt-5.5",
        output_language="English",
    )
    params_b = params_a.model_copy(update={"ticker": "MSFT"})

    try:
        service.start_queue(max_workers=1)
        task_a = service.create_analysis(user["id"], params_a, run_inline=False)
        task_b = service.create_analysis(user["id"], params_b, run_inline=False)
        service.enqueue_task(task_a["id"], params_a)
        service.enqueue_task(task_b["id"], params_b)

        assert runner.started.get(timeout=5) == "AAPL"
        assert repo.get_task_status(task_a["id"]) == "running"
        assert repo.get_task_status(task_b["id"]) == "queued"

        runner.releases["AAPL"].set()
        assert runner.started.get(timeout=5) == "MSFT"
        assert repo.get_task_status(task_a["id"]) == "completed"
        assert repo.get_task_status(task_b["id"]) == "running"

        runner.releases["MSFT"].set()
        deadline = time.time() + 5
        while time.time() < deadline and repo.get_task_status(task_b["id"]) != "completed":
            time.sleep(0.05)
        assert repo.get_task_status(task_b["id"]) == "completed"
    finally:
        for event in runner.releases.values():
            event.set()
        service.stop_queue()


def test_create_analysis_enqueues_background_work_when_not_inline(tmp_path: Path):
    db_path = tmp_path / "queued-api.sqlite3"
    settings = WebSettings(
        database_path=db_path,
        auth_secret="test-secret",
        runner_mode="demo",
        allow_registration=True,
        analysis_workers=1,
    )
    with TestClient(create_app(settings=settings, run_tasks_inline=False)) as client:
        headers = login(client)
        response = client.post(
            "/api/analyses",
            headers=headers,
            json={
                "ticker": "QQQ",
                "analysis_date": "2026-05-01",
                "analysts": ["market"],
                "research_depth": 1,
                "llm_provider": "openai",
                "quick_model": "gpt-5.4-mini",
                "deep_model": "gpt-5.5",
                "output_language": "English",
            },
        )

        assert response.status_code == 201
        task = response.json()
        assert task["status"] == "queued"

        deadline = time.time() + 5
        detail = client.get(f"/api/analyses/{task['id']}", headers=headers).json()
        while time.time() < deadline and detail["status"] != "completed":
            time.sleep(0.05)
            detail = client.get(f"/api/analyses/{task['id']}", headers=headers).json()

        assert detail["status"] == "completed"
        assert detail["parameters"]["ticker"] == "QQQ"


def test_schedule_trigger_uses_analysis_queue_when_not_inline(tmp_path: Path):
    class BlockingRunner:
        def __init__(self) -> None:
            self.started: queue.Queue[str] = queue.Queue()
            self.release = threading.Event()

        def run(self, params: AnalysisCreate, emit):
            emit(EventPayload(agent="System", event_type="task.started", message=f"start {params.ticker}"))
            self.started.put(params.ticker)
            assert self.release.wait(timeout=5), "timed out waiting to release scheduled analysis"
            emit(EventPayload(agent="System", event_type="task.completed", message=f"done {params.ticker}"))
            return RunnerResult(
                report_sections={"final_trade_decision": f"HOLD {params.ticker}"},
                final_decision={"decision": "HOLD", "confidence": None, "rationale": f"HOLD {params.ticker}", "raw_decision": f"HOLD {params.ticker}"},
            )

    repo = WebRepository(tmp_path / "schedule-queue.sqlite3")
    user = repo.create_user("schedule-queue@example.com", "correct horse battery staple")
    runner = BlockingRunner()
    service = AnalysisService(repo, runner)
    scheduler = SchedulerService(service)
    schedule = repo.create_schedule(
        user["id"],
        ScheduledAnalysisCreate(
            name="Queued schedule",
            ticker="NVDA",
            start_at="2026-05-01T09:30:00+00:00",
            interval="daily",
            analysts=["market"],
            research_depth=1,
            llm_provider="openai",
            quick_model="gpt-5.4-mini",
            deep_model="gpt-5.5",
            output_language="English",
        ),
    )

    try:
        service.start_queue(max_workers=1)
        execution = scheduler.execute_schedule(user["id"], schedule["id"], run_inline=False)

        assert execution is not None
        assert execution["status"] == "queued"
        assert execution["analysis_task_id"] is not None
        assert runner.started.get(timeout=5) == "NVDA"
        assert repo.get_task_status(execution["analysis_task_id"]) == "running"

        runner.release.set()
        deadline = time.time() + 5
        refreshed = repo.get_schedule_execution(execution["id"])
        while time.time() < deadline and refreshed and refreshed["status"] != "completed":
            time.sleep(0.05)
            refreshed = repo.get_schedule_execution(execution["id"])

        assert refreshed is not None
        assert refreshed["status"] == "completed"
        assert repo.get_task_status(execution["analysis_task_id"]) == "completed"
    finally:
        runner.release.set()
        service.stop_queue()


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
    assert history["items"][0]["parameters"]["ticker"] == "MSFT"
    assert history["items"][0]["parameters"]["analysts"] == ["fundamentals"]
    assert history["items"][0]["parameters"]["research_depth"] == 1
    assert history["items"][0]["parameters"]["quick_model"] == "gpt-5.4-mini"

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


def test_running_analysis_can_be_cancelled_and_reports_stale_metadata(tmp_path: Path):
    client, db_path = make_client(tmp_path)
    headers = login(client)

    create = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "MSFT",
            "analysis_date": "2026-05-01",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    ).json()
    task_id = create["id"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("update analysis_tasks set status = 'running', completed_at = null, error = null where id = ?", (task_id,))
        conn.execute("delete from final_decisions where task_id = ?", (task_id,))
        conn.execute("delete from report_sections where task_id = ?", (task_id,))
        conn.execute("update agent_event_logs set created_at = '2026-05-01T00:00:00+00:00' where task_id = ?", (task_id,))

    stale_response = client.get(f"/api/analyses/{task_id}?stale_after_seconds=1", headers=headers)
    assert stale_response.status_code == 200
    stale_task = stale_response.json()
    assert stale_task["stale"] is True
    assert stale_task["last_event_at"] == "2026-05-01T00:00:00+00:00"

    cancel = client.post(f"/api/analyses/{task_id}/cancel", headers=headers)
    assert cancel.status_code == 200
    cancelled = cancel.json()
    assert cancelled["status"] == "cancelled"
    assert cancelled["error"] == "cancelled by user"
    assert any(event["event_type"] == "task.cancelled" for event in cancelled["events"])

    repeated = client.post(f"/api/analyses/{task_id}/cancel", headers=headers)
    assert repeated.status_code == 409


def test_running_analysis_cannot_be_deleted_until_terminal(tmp_path: Path):
    client, db_path = make_client(tmp_path)
    headers = login(client)

    create = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "TSLA",
            "analysis_date": "2026-05-01",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    ).json()
    task_id = create["id"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("update analysis_tasks set status = 'running', completed_at = null, error = null where id = ?", (task_id,))

    response = client.delete(f"/api/analyses/{task_id}", headers=headers)

    assert response.status_code == 409
    detail = client.get(f"/api/analyses/{task_id}", headers=headers).json()
    assert detail["status"] == "running"


def test_running_analysis_can_be_paused_and_stream_ends(tmp_path: Path):
    client, db_path = make_client(tmp_path)
    headers = login(client)

    create = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "TSLA",
            "analysis_date": "2026-05-01",
            "analysts": ["market", "news"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    ).json()
    task_id = create["id"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("update analysis_tasks set status = 'running', completed_at = null, error = null where id = ?", (task_id,))
        conn.execute("delete from final_decisions where task_id = ?", (task_id,))
        conn.execute("delete from report_sections where task_id = ?", (task_id,))

    paused = client.post(f"/api/analyses/{task_id}/pause", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert any(event["event_type"] == "task.paused" for event in paused.json()["events"])

    repeated = client.post(f"/api/analyses/{task_id}/pause", headers=headers)
    assert repeated.status_code == 409

    events_response = client.get(f"/api/analyses/{task_id}/events", headers=headers)
    assert events_response.status_code == 200
    assert "event: task_event" in events_response.text
    assert "event: end" in events_response.text


def test_analysis_service_stops_when_task_is_paused_mid_run(tmp_path: Path):
    db_path = tmp_path / "web.sqlite3"
    repo = WebRepository(db_path)
    user = repo.create_user("pause@example.com", "correct horse battery staple")
    params = AnalysisCreate(
        ticker="SPY",
        analysis_date=date(2026, 5, 1),
        analysts=["market"],
        research_depth=1,
        llm_provider="openai",
        quick_model="gpt-5.4-mini",
        deep_model="gpt-5.5",
        output_language="English",
    )
    task = repo.create_task(user["id"], params)
    task_id = task["id"]

    class PausingRunner:
        def run(self, params, emit):
            emit(EventPayload(agent="System", event_type="task.started", message="start"))
            repo.update_task_status(task_id, "paused")
            emit(EventPayload(agent="Market Analyst", event_type="agent.message", message="should not persist"))
            return RunnerResult(
                report_sections={"market_report": "should not persist"},
                final_decision={"decision": "HOLD", "rationale": "should not persist", "raw_decision": "HOLD"},
            )

    service = AnalysisService(repo, PausingRunner())
    service.run_task(task_id, params)

    detail = repo.get_task_for_user(task_id, user["id"])
    assert detail["status"] == "paused"
    assert not detail.get("report_sections")
    assert not detail.get("final_decision")
    assert any(event["event_type"] == "task.started" for event in detail["events"])
    assert not any(event["message"] == "should not persist" for event in detail["events"])


def test_graph_runner_emits_each_debate_turn_with_round_metadata():
    runner = TradingAgentsGraphRunner()
    events: list[EventPayload] = []
    emitted: dict[str, int] = {}

    runner._emit_debate_updates(
        {
            "investment_debate_state": {
                "count": 1,
                "current_response": "Bull Analyst: first bullish argument",
                "history": "Bull Analyst: first bullish argument",
            },
            "risk_debate_state": {
                "count": 3,
                "latest_speaker": "Neutral Analyst",
                "current_neutral_response": "Neutral Analyst: balanced risk view",
                "history": "Aggressive Analyst: risk on\nConservative Analyst: risk off\nNeutral Analyst: balanced risk view",
            },
        },
        events.append,
        emitted,
    )

    assert [(event.agent, event.event_type, event.payload["round"]) for event in events] == [
        ("Bull Researcher", "debate.message", 1),
        ("Aggressive Risk Analyst", "debate.message", 1),
        ("Conservative Risk Analyst", "debate.message", 1),
        ("Neutral Risk Analyst", "debate.message", 1),
    ]
    assert events[0].payload["debate"] == "investment"
    assert events[1].payload["debate"] == "risk"
    assert events[0].message == "Bull Analyst: first bullish argument"
    assert events[3].message == "Neutral Analyst: balanced risk view"


def test_startup_marks_interrupted_running_analysis_failed(tmp_path: Path):
    client, db_path = make_client(tmp_path)
    headers = login(client)

    create = client.post(
        "/api/analyses",
        headers=headers,
        json={
            "ticker": "MSFT",
            "analysis_date": "2026-05-01",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    ).json()
    task_id = create["id"]
    with sqlite3.connect(db_path) as conn:
        conn.execute("update analysis_tasks set status = 'running', completed_at = null, error = null where id = ?", (task_id,))

    settings = WebSettings(
        database_path=db_path,
        auth_secret="test-secret",
        runner_mode="demo",
        allow_registration=True,
    )
    restarted = TestClient(create_app(settings=settings, run_tasks_inline=True))

    detail = restarted.get(f"/api/analyses/{task_id}", headers=headers).json()
    assert detail["status"] == "failed"
    assert detail["error"] == "analysis interrupted by server restart"
    assert any(event["event_type"] == "task.failed" and "server restart" in event["message"] for event in detail["events"])


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

    from tradingagents.default_config import DEFAULT_CONFIG
    monkeypatch.setitem(DEFAULT_CONFIG, "backend_url", "http://env-backend.example/v1")

    class FakeTradingAgentsGraph:
        def __init__(self, selected_analysts, config, debug=False):
            assert selected_analysts == ["market"]
            assert config["max_debate_rounds"] == 1
            assert config["backend_url"] == "http://env-backend.example/v1"
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


def test_web_graph_runner_applies_llm_timeout_settings(monkeypatch):
    import tradingagents.graph.trading_graph as trading_graph_module

    captured_config = {}

    class FakeTradingAgentsGraph:
        def __init__(self, selected_analysts, config, debug=False):
            captured_config.update(config)
            self.memory_log = type("Memory", (), {"get_past_context": lambda self, ticker: ""})()
            self.propagator = type(
                "Propagator",
                (),
                {
                    "create_initial_state": lambda self, ticker, analysis_date, past_context=None: {},
                    "get_graph_args": lambda self: {},
                },
            )()
            self.graph = type(
                "CompiledGraph",
                (),
                {
                    "stream": lambda self, initial_state, **kwargs: iter([
                        {"final_trade_decision": "HOLD SPY", "messages": []}
                    ]),
                },
            )()

        def process_signal(self, raw_signal):
            return "HOLD"

    monkeypatch.setenv("TRADINGAGENTS_WEB_LLM_TIMEOUT", "33")
    monkeypatch.setenv("TRADINGAGENTS_WEB_LLM_MAX_RETRIES", "4")
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
    )

    TradingAgentsGraphRunner().run(params, lambda event: None)

    assert captured_config["llm_timeout"] == 33
    assert captured_config["llm_max_retries"] == 4


def test_real_graph_runner_retries_transient_incomplete_chunked_stream(monkeypatch):
    """A transient upstream chunked-read failure should retry the graph stream once."""

    import tradingagents.graph.trading_graph as trading_graph_module

    emitted: list[EventPayload] = []
    attempts = {"count": 0}

    class FakeMemoryLog:
        def get_past_context(self, ticker):
            return ""

    class FakePropagator:
        def create_initial_state(self, ticker, analysis_date, past_context=None):
            return {"ticker": ticker, "analysis_date": analysis_date, "past_context": past_context}

        def get_graph_args(self):
            return {}

    class FakeCompiledGraph:
        def stream(self, initial_state, **kwargs):
            attempts["count"] += 1
            if attempts["count"] == 1:
                yield {"market_report": "partial market report", "messages": []}
                raise RuntimeError("peer closed connection without sending complete message body (incomplete chunked read)")
            yield {
                "market_report": "final market report",
                "investment_plan": "final research plan",
                "trader_investment_plan": "final trader plan",
                "final_trade_decision": "HOLD SPY after retry",
                "messages": [],
            }

    class FakeTradingAgentsGraph:
        def __init__(self, selected_analysts, config, debug=False):
            self.config = config
            self.memory_log = FakeMemoryLog()
            self.propagator = FakePropagator()
            self.graph = FakeCompiledGraph()
            self.curr_state = None

        def process_signal(self, raw_signal):
            return "HOLD"

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
    )

    result = TradingAgentsGraphRunner().run(params, emitted.append)

    assert attempts["count"] == 2
    assert result.final_decision["decision"] == "HOLD"
    assert any(event.event_type == "task.retrying" for event in emitted)


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


def test_production_settings_reject_unsafe_defaults_and_bootstrap_user(tmp_path: Path):
    with pytest.raises(ValueError, match="self-registration"):
        create_app(
            settings=WebSettings(
                database_path=tmp_path / "open.sqlite3",
                web_env="production",
                auth_secret="strong-production-secret",
                allow_registration=True,
                cors_origins=("https://app.example.com",),
            )
        )
    with pytest.raises(ValueError, match="auth secret"):
        create_app(
            settings=WebSettings(
                database_path=tmp_path / "secret.sqlite3",
                web_env="production",
                auth_secret="change-me-local-dev-secret",
                allow_registration=False,
                cors_origins=("https://app.example.com",),
            )
        )
    with pytest.raises(ValueError, match="CORS"):
        create_app(
            settings=WebSettings(
                database_path=tmp_path / "cors.sqlite3",
                web_env="production",
                auth_secret="strong-production-secret",
                allow_registration=False,
                cors_origins=("*",),
            )
        )

    settings = WebSettings(
        database_path=tmp_path / "safe.sqlite3",
        web_env="production",
        auth_secret="strong-production-secret",
        allow_registration=False,
        cors_origins=("https://app.example.com",),
        bootstrap_user_email="admin@example.com",
        bootstrap_user_password="correct horse battery staple",
    )
    client = TestClient(create_app(settings=settings, run_tasks_inline=True))
    assert client.post("/api/auth/register", json={"email": "new@example.com", "password": "correct horse battery staple"}).status_code == 403
    login_response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "correct horse battery staple"},
    )
    assert login_response.status_code == 200


def test_rate_limits_and_security_audit_logs_cover_high_risk_actions(tmp_path: Path):
    db_path = tmp_path / "web.sqlite3"
    settings = WebSettings(
        database_path=db_path,
        auth_secret="test-secret",
        runner_mode="demo",
        allow_registration=True,
        rate_limit_window_seconds=60,
        auth_rate_limit=20,
        mutation_rate_limit=20,
        analysis_rate_limit=1,
        intervention_rate_limit=1,
    )
    client = TestClient(create_app(settings=settings, run_tasks_inline=True))
    headers = login(client)

    payload = {
        "ticker": "SPY",
        "analysis_date": "2026-05-01",
        "analysts": ["market"],
        "research_depth": 1,
        "llm_provider": "openai",
        "quick_model": "gpt-5.4-mini",
        "deep_model": "gpt-5.5",
        "output_language": "English",
    }
    first = client.post("/api/analyses", headers=headers, json=payload)
    assert first.status_code == 201
    limited = client.post("/api/analyses", headers=headers, json={**payload, "ticker": "AAPL"})
    assert limited.status_code == 429

    intervention = client.post(
        "/api/interventions",
        headers=headers,
        json={"source_analysis_task_id": first.json()["id"], "target_agent_name": "Market Analyst"},
    ).json()
    schedule = client.post(
        "/api/schedules",
        headers=headers,
        json={
            "name": "Audited trigger",
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
    assert client.post(f"/api/schedules/{schedule['id']}/trigger", headers=headers).status_code == 201
    assert client.post(f"/api/interventions/{intervention['id']}/run", headers=headers).status_code == 201
    assert client.post(f"/api/interventions/{intervention['id']}/run", headers=headers).status_code == 429

    with sqlite3.connect(db_path) as conn:
        events = {row[0] for row in conn.execute("select event_type from audit_logs").fetchall()}
    assert {
        "auth.login.success",
        "analysis.create",
        "schedule.create",
        "schedule.trigger",
        "intervention.create",
        "intervention.run",
        "rate_limit.exceeded",
    } <= events


def test_export_delete_retention_are_owner_scoped(tmp_path: Path):
    client, db_path = make_client(tmp_path)
    headers = login(client)
    other_register = client.post(
        "/api/auth/register",
        json={"email": "phase5-other@example.com", "password": "correct horse battery staple"},
    )
    assert other_register.status_code == 201
    other_login = client.post(
        "/api/auth/login",
        json={"email": "phase5-other@example.com", "password": "correct horse battery staple"},
    )
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    payload = {
        "ticker": "SPY",
        "analysis_date": "2026-05-01",
        "analysts": ["market"],
        "research_depth": 1,
        "llm_provider": "openai",
        "quick_model": "gpt-5.4-mini",
        "deep_model": "gpt-5.5",
        "output_language": "English",
    }
    mine = client.post("/api/analyses", headers=headers, json=payload).json()
    theirs = client.post("/api/analyses", headers=other_headers, json={**payload, "ticker": "AAPL"}).json()
    memory_id = client.get("/api/memories", headers=headers, params={"agent": "Market Analyst"}).json()["items"][0]["id"]
    intervention = client.post(
        "/api/interventions",
        headers=headers,
        json={"source_analysis_task_id": mine["id"], "target_agent_name": "Market Analyst"},
    ).json()

    exported = client.get("/api/account/export", headers=headers)
    assert exported.status_code == 200
    data = exported.json()
    assert [item["id"] for item in data["analyses"]] == [mine["id"]]
    assert all(item["user_id"] != 2 for item in data["memories"])
    assert [item["id"] for item in data["interventions"]] == [intervention["id"]]

    assert client.post(f"/api/memories/{memory_id}/archive", headers=headers).status_code == 200
    assert client.delete(f"/api/analyses/{theirs['id']}", headers=headers).status_code == 404
    assert client.delete(f"/api/analyses/{mine['id']}", headers=headers).status_code == 204
    assert client.get(f"/api/analyses/{theirs['id']}", headers=other_headers).status_code == 200

    with sqlite3.connect(db_path) as conn:
        events = {row[0] for row in conn.execute("select event_type from audit_logs").fetchall()}
    assert {"account.export", "analysis.delete", "memory.archive"} <= events


def test_sqlite_backup_helper_and_idempotent_initialization(tmp_path: Path):
    db_path = tmp_path / "web.sqlite3"
    repo = WebRepository(db_path)
    repo.create_user("backup@example.com", "correct horse battery staple")
    WebRepository(db_path)
    backup_path = backup_sqlite_database(db_path, tmp_path / "backup.sqlite3")

    assert backup_path.exists()
    with sqlite3.connect(backup_path) as conn:
        assert conn.execute("select count(*) from users").fetchone()[0] == 1
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'").fetchall()}
    assert {"users", "audit_logs", "schema_migrations"} <= tables


def test_workspace_personal_migration_roles_and_cross_workspace_isolation(tmp_path: Path):
    client, _ = make_client(tmp_path)
    owner_headers = login(client)
    client.post(
        "/api/auth/register",
        json={"email": "workspace-member@example.com", "password": "correct horse battery staple"},
    )
    member_login = client.post(
        "/api/auth/login",
        json={"email": "workspace-member@example.com", "password": "correct horse battery staple"},
    )
    member_headers = {"Authorization": f"Bearer {member_login.json()['access_token']}"}

    personal = client.get("/api/workspaces", headers=owner_headers)
    assert personal.status_code == 200
    assert personal.json()["items"][0]["kind"] == "personal"
    assert personal.json()["items"][0]["role"] == "owner"

    workspace = client.post("/api/workspaces", headers=owner_headers, json={"name": "Research Desk"}).json()
    viewer = client.post(
        f"/api/workspaces/{workspace['id']}/members",
        headers=owner_headers,
        json={"email": "workspace-member@example.com", "role": "viewer"},
    )
    assert viewer.status_code == 201
    denied = client.post(
        "/api/analyses",
        headers=member_headers,
        json={
            "workspace_id": workspace["id"],
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
    assert denied.status_code == 403

    promoted = client.patch(
        f"/api/workspaces/{workspace['id']}/members/{viewer.json()['user_id']}",
        headers=owner_headers,
        json={"role": "member"},
    )
    assert promoted.status_code == 200
    created = client.post(
        "/api/analyses",
        headers=member_headers,
        json={
            "workspace_id": workspace["id"],
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
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert client.get(f"/api/analyses/{task_id}", headers=owner_headers).status_code == 200

    private_workspace = client.post("/api/workspaces", headers=owner_headers, json={"name": "Private Desk"}).json()
    private_task = client.post(
        "/api/analyses",
        headers=owner_headers,
        json={
            "workspace_id": private_workspace["id"],
            "ticker": "AAPL",
            "analysis_date": "2026-05-01",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
            "output_language": "English",
        },
    ).json()
    assert client.get(f"/api/analyses/{private_task['id']}", headers=member_headers).status_code == 404


def test_workspace_owner_retention_and_due_schedule_scope(tmp_path: Path):
    client, _ = make_client(tmp_path)
    headers = login(client)
    first = client.post("/api/workspaces", headers=headers, json={"name": "First Due Desk"}).json()
    second = client.post("/api/workspaces", headers=headers, json={"name": "Second Due Desk"}).json()

    workspaces = client.get("/api/workspaces", headers=headers).json()["items"]
    personal_owner_id = next(workspace for workspace in workspaces if workspace["kind"] == "personal")["created_by_user_id"]
    orphaned_owner = client.patch(
        f"/api/workspaces/{first['id']}/members/{personal_owner_id}",
        headers=headers,
        json={"role": "admin"},
    )
    assert orphaned_owner.status_code == 409

    schedule_payload = {
        "start_at": "2026-05-01T09:30:00+00:00",
        "interval": "daily",
        "analysts": ["market"],
        "research_depth": 1,
        "llm_provider": "openai",
        "quick_model": "gpt-5.4-mini",
        "deep_model": "gpt-5.5",
        "output_language": "English",
    }
    first_schedule = client.post(
        "/api/schedules",
        headers=headers,
        json={**schedule_payload, "workspace_id": first["id"], "name": "First due", "ticker": "SPY"},
    ).json()
    second_schedule = client.post(
        "/api/schedules",
        headers=headers,
        json={**schedule_payload, "workspace_id": second["id"], "name": "Second due", "ticker": "AAPL"},
    ).json()

    run_due = client.post(
        "/api/scheduler/run-due",
        headers=headers,
        params={"workspace_id": first["id"]},
        json={"now": "2026-05-02T10:00:00+00:00"},
    )
    assert run_due.status_code == 200
    executions = run_due.json()["executions"]
    assert [execution["schedule_id"] for execution in executions] == [first_schedule["id"]]
    assert client.get(f"/api/schedules/{second_schedule['id']}", headers=headers).json()["last_run_at"] is None


def test_workspace_governance_audit_filters_and_export_scope(tmp_path: Path):
    client, _ = make_client(tmp_path)
    headers = login(client)
    first = client.post("/api/workspaces", headers=headers, json={"name": "First"}).json()
    second = client.post("/api/workspaces", headers=headers, json={"name": "Second"}).json()
    payload = {
        "ticker": "SPY",
        "analysis_date": "2026-05-01",
        "analysts": ["market"],
        "research_depth": 1,
        "llm_provider": "openai",
        "quick_model": "gpt-5.4-mini",
        "deep_model": "gpt-5.5",
        "output_language": "English",
    }
    client.post("/api/analyses", headers=headers, json={**payload, "workspace_id": first["id"]})
    client.post("/api/analyses", headers=headers, json={**payload, "workspace_id": second["id"], "ticker": "MSFT"})

    audit = client.get(
        "/api/governance/audit",
        headers=headers,
        params={"workspace_id": first["id"], "event_type": "analysis.create"},
    )
    assert audit.status_code == 200
    assert {item["workspace_id"] for item in audit.json()["items"]} == {first["id"]}

    exported = client.get(f"/api/workspaces/{first['id']}/export", headers=headers)
    assert exported.status_code == 200
    data = exported.json()
    assert data["workspace"]["id"] == first["id"]
    assert [item["parameters"]["ticker"] for item in data["analyses"]] == ["SPY"]


def test_real_runner_budget_guardrail_blocks_and_audits_analysis(tmp_path: Path):
    settings = WebSettings(
        database_path=tmp_path / "web.sqlite3",
        auth_secret="test-secret",
        runner_mode="real",
        allow_registration=True,
        real_runner_user_analysis_limit=0,
        real_runner_workspace_analysis_limit=0,
    )
    client = TestClient(create_app(settings=settings, run_tasks_inline=True))
    headers = login(client)
    blocked = client.post(
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
    assert blocked.status_code == 402
    audit = client.get("/api/governance/audit", headers=headers, params={"event_type": "cost.blocked"})
    assert audit.status_code == 200
    assert audit.json()["items"][0]["metadata"]["reason"] == "user budget exceeded"


def test_real_runner_budget_guardrail_blocks_continuation_and_schedule_trigger(tmp_path: Path):
    settings = WebSettings(
        database_path=tmp_path / "web.sqlite3",
        auth_secret="test-secret",
        runner_mode="demo",
        allow_registration=True,
        real_runner_user_analysis_limit=-1,
        real_runner_workspace_analysis_limit=-1,
    )
    client = TestClient(create_app(settings=settings, run_tasks_inline=True))
    headers = login(client)
    payload = {
        "ticker": "SPY",
        "analysis_date": "2026-05-01",
        "analysts": ["market"],
        "research_depth": 1,
        "llm_provider": "openai",
        "quick_model": "gpt-5.4-mini",
        "deep_model": "gpt-5.5",
        "output_language": "English",
    }
    analysis = client.post("/api/analyses", headers=headers, json=payload).json()
    intervention = client.post(
        "/api/interventions",
        headers=headers,
        json={"source_analysis_task_id": analysis["id"], "target_agent_name": "Market Analyst"},
    ).json()
    schedule = client.post(
        "/api/schedules",
        headers=headers,
        json={
            "name": "Budget trigger",
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

    object.__setattr__(settings, "runner_mode", "real")
    object.__setattr__(settings, "real_runner_user_analysis_limit", 0)
    continuation = client.post(f"/api/interventions/{intervention['id']}/run", headers=headers)
    triggered = client.post(f"/api/schedules/{schedule['id']}/trigger", headers=headers)

    assert continuation.status_code == 402
    assert triggered.status_code == 402
    audit = client.get("/api/governance/audit", headers=headers, params={"event_type": "cost.blocked"})
    assert len(audit.json()["items"]) >= 2


def test_backup_helper_rejects_missing_source_database(tmp_path: Path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(FileNotFoundError):
        backup_sqlite_database(missing, tmp_path / "backup.sqlite3")


def test_sqlite_to_postgres_migration_plan_apply_validate_is_idempotent(tmp_path: Path):
    source_path = tmp_path / "source.sqlite3"
    source = WebRepository(source_path)
    user = source.create_user("migrate@example.com", "correct horse battery staple")
    task = source.create_task(
        user["id"],
        {
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
    source.append_audit_log("analysis.create", user_id=user["id"], workspace_id=task["workspace_id"], resource_type="analysis", resource_id=task["id"])
    backup_path = backup_sqlite_database(source_path, tmp_path / "backup.sqlite3")

    plan = plan_sqlite_to_postgres_migration(source_path, backup_path=backup_path)
    assert plan["tables"]["users"]["row_count"] == 1
    assert plan["tables"]["analysis_tasks"]["row_count"] == 1
    assert plan["backup"]["ok"] is True

    target_path = tmp_path / "target.sqlite3"
    WebRepository(target_path)
    applied = apply_sqlite_to_postgres_migration(source_path, target_path, backup_path=backup_path)
    assert applied["applied"] is True
    assert applied["tables"]["users"]["inserted_rows"] == 1
    assert applied["tables"]["analysis_tasks"]["inserted_rows"] == 1

    second = apply_sqlite_to_postgres_migration(source_path, target_path, backup_path=backup_path)
    assert second["tables"]["users"]["inserted_rows"] == 0
    assert second["tables"]["analysis_tasks"]["inserted_rows"] == 0

    validation = validate_sqlite_to_postgres_migration(source_path, target_path)
    assert validation["ok"] is True
    assert validation["tables"]["analysis_tasks"]["source_count"] == validation["tables"]["analysis_tasks"]["target_count"] == 1


def test_usage_ledger_reconciliation_repairs_coordinator_drift(tmp_path: Path):
    repository = WebRepository(tmp_path / "web.sqlite3")
    user = repository.create_user("ledger@example.com", "correct horse battery staple")
    workspace_id = repository.get_personal_workspace_id(user["id"])
    first = repository.record_usage_ledger(
        user_id=user["id"],
        workspace_id=workspace_id,
        resource_type="analysis",
        resource_id="task-1",
        period_kind="daily",
        occurred_at="2026-05-05T10:00:00+00:00",
    )
    repository.record_usage_ledger(
        user_id=user["id"],
        workspace_id=workspace_id,
        resource_type="analysis",
        resource_id="task-2",
        period_kind="daily",
        occurred_at="2026-05-05T11:00:00+00:00",
    )
    coordinator = InMemoryCoordinator(namespace="phase8")
    coordinator.set_budget_usage(
        user_id=user["id"],
        workspace_id=workspace_id,
        user_count=0,
        workspace_count=5,
        period_key=first["window_key"],
    )

    result = reconcile_usage_ledger(
        repository,
        coordinator,
        period_kind="daily",
        as_of="2026-05-05T23:59:00+00:00",
        repair=True,
        user_id=user["id"],
        workspace_id=workspace_id,
    )

    assert result["window_key"] == first["window_key"]
    assert result["repair_applied"] is True
    assert result["drift"][0]["expected_user_count"] == 2
    assert result["drift"][0]["expected_workspace_count"] == 2
    assert coordinator.describe_budget(user_id=user["id"], workspace_id=workspace_id, period_key=first["window_key"]) == {
        "user": 2,
        "workspace": 2,
    }


def test_real_runner_analysis_records_usage_ledger_entries(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(web_main, "TradingAgentsGraphRunner", DemoAnalysisRunner)
    settings = WebSettings(
        database_path=tmp_path / "web.sqlite3",
        auth_secret="test-secret",
        runner_mode="real",
        allow_registration=True,
        real_runner_user_analysis_limit=5,
        real_runner_workspace_analysis_limit=5,
        real_runner_budget_period="daily",
    )
    client = TestClient(create_app(settings=settings, run_tasks_inline=True))
    headers = login(client)

    response = client.post(
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

    assert response.status_code == 201
    repository = WebRepository(tmp_path / "web.sqlite3")
    entries = repository.list_usage_ledger()
    assert len(entries) == 1
    assert entries[0]["resource_type"] == "analysis"
    assert entries[0]["resource_id"] == str(response.json()["id"])
    assert entries[0]["period_kind"] == "daily"
