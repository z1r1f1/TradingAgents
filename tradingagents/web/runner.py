from __future__ import annotations

from typing import Any, Callable, Protocol

from .schemas import AnalysisCreate, EventPayload, RunnerResult

EventCallback = Callable[[EventPayload], None]


class AnalysisRunner(Protocol):
    def run(self, params: AnalysisCreate, emit: EventCallback) -> RunnerResult: ...


class DemoAnalysisRunner:
    """Deterministic runner for tests and local UI smoke checks without LLM/network calls."""

    AGENT_NAMES = {
        "market": "Market Analyst",
        "social": "Social Analyst",
        "news": "News Analyst",
        "fundamentals": "Fundamentals Analyst",
    }

    def run(self, params: AnalysisCreate, emit: EventCallback) -> RunnerResult:
        sections: dict[str, str] = {}
        emit(EventPayload(agent="System", event_type="task.started", message=f"Started analysis for {params.ticker}"))
        for analyst in params.analysts:
            agent = self.AGENT_NAMES[analyst]
            report_key = "sentiment_report" if analyst == "social" else f"{analyst}_report"
            report = f"Demo {agent} report for {params.ticker} on {params.analysis_date}."
            sections[report_key] = report
            emit(EventPayload(agent=agent, event_type="agent.started", message=f"{agent} started"))
            emit(EventPayload(agent=agent, event_type="agent.message", message=report, payload={"section": report_key}))
            emit(EventPayload(agent=agent, event_type="agent.completed", message=f"{agent} completed"))
        sections["investment_plan"] = f"Research manager recommends monitoring {params.ticker}."
        sections["trader_investment_plan"] = f"Trader plan for {params.ticker}: controlled position sizing."
        final_text = f"HOLD {params.ticker}: demo decision for {params.output_language} output."
        sections["final_trade_decision"] = final_text
        emit(EventPayload(agent="Research Manager", event_type="agent.completed", message=sections["investment_plan"]))
        emit(EventPayload(agent="Trader", event_type="agent.completed", message=sections["trader_investment_plan"]))
        emit(EventPayload(agent="Portfolio Manager", event_type="agent.completed", message=final_text))
        emit(EventPayload(agent="System", event_type="task.completed", message=f"Completed analysis for {params.ticker}"))
        return RunnerResult(
            report_sections=sections,
            final_decision={
                "decision": "HOLD",
                "confidence": "demo",
                "rationale": final_text,
                "raw_decision": final_text,
            },
        )


class TradingAgentsGraphRunner:
    """Production runner seam around the existing core graph; CLI behavior is untouched."""

    def run(self, params: AnalysisCreate, emit: EventCallback) -> RunnerResult:
        emit(EventPayload(agent="System", event_type="task.started", message=f"Starting graph for {params.ticker}"))
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = DEFAULT_CONFIG.copy()
        config.update(
            {
                "max_debate_rounds": params.research_depth,
                "max_risk_discuss_rounds": params.research_depth,
                "quick_think_llm": params.quick_model,
                "deep_think_llm": params.deep_model,
                "backend_url": params.backend_url,
                "llm_provider": params.llm_provider.lower(),
                "output_language": params.output_language,
                "google_thinking_level": params.google_thinking_level,
                "openai_reasoning_effort": params.openai_reasoning_effort,
                "anthropic_effort": params.anthropic_effort,
            }
        )
        graph = TradingAgentsGraph(params.analysts, config=config, debug=False)
        final_state, decision = graph.propagate(params.ticker, params.analysis_date.isoformat())
        sections = self._sections_from_state(final_state)
        for section, content in sections.items():
            emit(EventPayload(agent=self._agent_for_section(section), event_type="report.section", message=str(content)[:500], payload={"section": section}))
        raw = final_state.get("final_trade_decision", str(decision))
        emit(EventPayload(agent="Portfolio Manager", event_type="agent.completed", message=str(raw)[:500]))
        return RunnerResult(
            report_sections=sections,
            final_decision={"decision": str(decision).upper(), "confidence": None, "rationale": str(raw), "raw_decision": str(raw)},
        )

    def _sections_from_state(self, final_state: dict[str, Any]) -> dict[str, str]:
        keys = [
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
        ]
        return {key: str(final_state[key]) for key in keys if final_state.get(key)}

    def _agent_for_section(self, section: str) -> str:
        return {
            "market_report": "Market Analyst",
            "sentiment_report": "Social Analyst",
            "news_report": "News Analyst",
            "fundamentals_report": "Fundamentals Analyst",
            "investment_plan": "Research Manager",
            "trader_investment_plan": "Trader",
            "final_trade_decision": "Portfolio Manager",
        }.get(section, "System")
