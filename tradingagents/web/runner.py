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
        final_state = self._stream_graph(params, graph, emit)
        sections = self._sections_from_state(final_state)
        raw = final_state.get("final_trade_decision", "")
        decision = graph.process_signal(raw)
        if hasattr(graph, "curr_state"):
            graph.curr_state = final_state
        self._persist_core_side_effects(params, graph, final_state)
        emit(EventPayload(agent="Portfolio Manager", event_type="agent.completed", message=str(raw)[:500]))
        emit(EventPayload(agent="System", event_type="task.completed", message=f"Completed graph for {params.ticker}"))
        return RunnerResult(
            report_sections=sections,
            final_decision={"decision": str(decision).upper(), "confidence": None, "rationale": str(raw), "raw_decision": str(raw)},
        )

    def _stream_graph(self, params: AnalysisCreate, graph: Any, emit: EventCallback) -> dict[str, Any]:
        trade_date = params.analysis_date.isoformat()
        if hasattr(graph, "ticker"):
            graph.ticker = params.ticker
        if hasattr(graph, "_resolve_pending_entries"):
            graph._resolve_pending_entries(params.ticker)
        past_context = ""
        if hasattr(graph, "memory_log") and hasattr(graph.memory_log, "get_past_context"):
            past_context = graph.memory_log.get_past_context(params.ticker)
        init_agent_state = graph.propagator.create_initial_state(
            params.ticker,
            trade_date,
            past_context=past_context,
        )
        args = graph.propagator.get_graph_args()
        final_state: dict[str, Any] | None = None
        emitted_sections: dict[str, str] = {}
        for chunk in graph.graph.stream(init_agent_state, **args):
            final_state = chunk
            self._emit_messages(chunk, emit)
            self._emit_report_sections(chunk, emit, emitted_sections)
        if not final_state:
            raise RuntimeError("TradingAgents graph produced no final state")
        return final_state

    def _emit_report_sections(self, state: dict[str, Any], emit: EventCallback, emitted_sections: dict[str, str]) -> None:
        for section, content in self._sections_from_state(state).items():
            text = str(content)
            if emitted_sections.get(section) == text:
                continue
            emitted_sections[section] = text
            emit(
                EventPayload(
                    agent=self._agent_for_section(section),
                    event_type="report.section",
                    message=text[:500],
                    payload={"section": section},
                )
            )

    def _emit_messages(self, state: dict[str, Any], emit: EventCallback) -> None:
        for message in state.get("messages", []) or []:
            content = getattr(message, "content", None)
            if isinstance(content, list):
                content = " ".join(str(item.get("text", item)) if isinstance(item, dict) else str(item) for item in content)
            if content:
                emit(EventPayload(agent="Graph", event_type="agent.message", message=str(content)[:500]))
            for tool_call in getattr(message, "tool_calls", []) or []:
                name = tool_call.get("name") if isinstance(tool_call, dict) else getattr(tool_call, "name", "tool")
                args = tool_call.get("args") if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
                emit(EventPayload(agent="Graph", event_type="tool.call", message=str(name), payload={"args": args}))

    def _persist_core_side_effects(self, params: AnalysisCreate, graph: Any, final_state: dict[str, Any]) -> None:
        trade_date = params.analysis_date.isoformat()
        if hasattr(graph, "_log_state"):
            graph._log_state(trade_date, final_state)
        if hasattr(graph, "memory_log") and hasattr(graph.memory_log, "store_decision") and final_state.get("final_trade_decision"):
            graph.memory_log.store_decision(
                ticker=params.ticker,
                trade_date=trade_date,
                final_trade_decision=final_state["final_trade_decision"],
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
