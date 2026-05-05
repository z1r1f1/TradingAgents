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
            assert (ticker, analysis_date, past_context) == ("SPY", "2026-05-01", "past context")
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
