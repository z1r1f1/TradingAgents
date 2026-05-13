from __future__ import annotations

import os
import re
from typing import Any, Callable, Protocol

from .schemas import AnalysisCreate, EventPayload, RunnerResult

EventCallback = Callable[[EventPayload], None]


class AnalysisRunner(Protocol):
    def run(self, params: AnalysisCreate, emit: EventCallback) -> RunnerResult: ...


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _graph_max_attempts() -> int:
    try:
        return max(1, int(os.getenv("TRADINGAGENTS_WEB_GRAPH_MAX_ATTEMPTS", "2")))
    except ValueError:
        return 2


def _is_transient_stream_error(exc: BaseException) -> bool:
    messages: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        messages.append(f"{type(current).__name__}: {current}".lower())
        current = current.__cause__ or current.__context__
    text = " | ".join(messages)
    return any(
        marker in text
        for marker in (
            "incomplete chunked read",
            "peer closed connection",
            "server disconnected",
            "connection reset",
            "remote protocol error",
            "read timeout",
            "readerror",
            "api connection error",
        )
    )


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
                "llm_provider": params.llm_provider.lower(),
                "output_language": params.output_language,
                "google_thinking_level": params.google_thinking_level,
                "openai_reasoning_effort": params.openai_reasoning_effort,
                "anthropic_effort": params.anthropic_effort,
                "checkpoint_enabled": _env_bool("TRADINGAGENTS_WEB_CHECKPOINT_ENABLED", default=True),
            }
        )
        if params.backend_url:
            config["backend_url"] = params.backend_url
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
        if params.memory_context:
            past_context = f"{past_context}\n\n{params.memory_context}" if past_context else params.memory_context
        init_agent_state = graph.propagator.create_initial_state(
            params.ticker,
            trade_date,
            past_context=past_context,
        )
        args = graph.propagator.get_graph_args()
        final_state: dict[str, Any] | None = None
        emitted_sections: dict[str, str] = {}
        emitted_debate_counts: dict[str, int] = {}
        checkpoint_ctx = self._enable_checkpointing(params, graph, args)
        max_attempts = _graph_max_attempts()
        try:
            for attempt in range(1, max_attempts + 1):
                try:
                    for chunk in graph.graph.stream(init_agent_state, **args):
                        final_state = chunk
                        self._emit_messages(chunk, emit)
                        self._emit_debate_updates(chunk, emit, emitted_debate_counts)
                        self._emit_report_sections(chunk, emit, emitted_sections)
                    break
                except Exception as exc:
                    if attempt >= max_attempts or not _is_transient_stream_error(exc):
                        raise
                    emit(
                        EventPayload(
                            agent="System",
                            event_type="task.retrying",
                            message=f"Transient upstream stream error; retrying graph ({attempt}/{max_attempts - 1}): {exc}",
                        )
                    )
        finally:
            if checkpoint_ctx is not None:
                checkpoint_ctx.__exit__(None, None, None)
                if hasattr(graph, "workflow"):
                    graph.graph = graph.workflow.compile()
        if not final_state:
            raise RuntimeError("TradingAgents graph produced no final state")
        return final_state

    def _enable_checkpointing(self, params: AnalysisCreate, graph: Any, args: dict[str, Any]):
        if not getattr(graph, "config", {}).get("checkpoint_enabled"):
            return None
        if not hasattr(graph, "workflow"):
            return None
        from tradingagents.graph.checkpointer import get_checkpointer, thread_id

        checkpoint_ctx = get_checkpointer(graph.config["data_cache_dir"], params.ticker)
        saver = checkpoint_ctx.__enter__()
        graph.graph = graph.workflow.compile(checkpointer=saver)
        args.setdefault("config", {}).setdefault("configurable", {})["thread_id"] = thread_id(
            params.ticker,
            params.analysis_date.isoformat(),
        )
        return checkpoint_ctx

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

    def _emit_debate_updates(self, state: dict[str, Any], emit: EventCallback, emitted_counts: dict[str, int]) -> None:
        self._emit_debate_state(
            debate_name="investment",
            debate_state=state.get("investment_debate_state") or {},
            participant_count=2,
            emitted_counts=emitted_counts,
            speaker_agents={
                "Bull Analyst": "Bull Researcher",
                "Bear Analyst": "Bear Researcher",
            },
            current_response_keys=["current_response"],
            latest_speaker_key=None,
            emit=emit,
        )
        self._emit_debate_state(
            debate_name="risk",
            debate_state=state.get("risk_debate_state") or {},
            participant_count=3,
            emitted_counts=emitted_counts,
            speaker_agents={
                "Aggressive Analyst": "Aggressive Risk Analyst",
                "Conservative Analyst": "Conservative Risk Analyst",
                "Neutral Analyst": "Neutral Risk Analyst",
            },
            current_response_keys=[
                "current_aggressive_response",
                "current_conservative_response",
                "current_neutral_response",
            ],
            latest_speaker_key="latest_speaker",
            emit=emit,
        )

    def _emit_debate_state(
        self,
        *,
        debate_name: str,
        debate_state: dict[str, Any],
        participant_count: int,
        emitted_counts: dict[str, int],
        speaker_agents: dict[str, str],
        current_response_keys: list[str],
        latest_speaker_key: str | None,
        emit: EventCallback,
    ) -> None:
        count = int(debate_state.get("count") or 0)
        already_emitted = emitted_counts.get(debate_name, 0)
        if count <= already_emitted:
            return

        turns = self._split_debate_history(str(debate_state.get("history") or ""), list(speaker_agents))
        if len(turns) < count:
            fallback = self._current_debate_response(debate_state, current_response_keys, latest_speaker_key)
            if fallback:
                turns.append(fallback)

        for turn_index in range(already_emitted + 1, count + 1):
            text = turns[turn_index - 1] if len(turns) >= turn_index else ""
            if not text:
                continue
            speaker = self._speaker_from_text(text, speaker_agents) or self._speaker_from_latest_state(debate_state, latest_speaker_key, speaker_agents)
            agent = speaker_agents.get(speaker or "", speaker or "Debate Analyst")
            emit(
                EventPayload(
                    agent=agent,
                    event_type="debate.message",
                    message=text,
                    payload={
                        "debate": debate_name,
                        "round": ((turn_index - 1) // participant_count) + 1,
                        "turn": turn_index,
                        "speaker": speaker or agent,
                    },
                )
            )
        emitted_counts[debate_name] = count

    def _current_debate_response(
        self,
        debate_state: dict[str, Any],
        current_response_keys: list[str],
        latest_speaker_key: str | None,
    ) -> str:
        if latest_speaker_key:
            latest_speaker = str(debate_state.get(latest_speaker_key) or "")
            for key in current_response_keys:
                response = str(debate_state.get(key) or "")
                if response and (not latest_speaker or response.startswith(latest_speaker)):
                    return response
        for key in current_response_keys:
            response = str(debate_state.get(key) or "")
            if response:
                return response
        return ""

    def _split_debate_history(self, history: str, speaker_names: list[str]) -> list[str]:
        if not history.strip():
            return []
        speaker_pattern = "|".join(re.escape(name) for name in speaker_names)
        matches = list(re.finditer(rf"(?m)(?:^|\n)({speaker_pattern}):", history))
        if not matches:
            return [history.strip()]
        turns: list[str] = []
        for index, match in enumerate(matches):
            start = match.start()
            if history[start:start + 1] == "\n":
                start += 1
            end = matches[index + 1].start() if index + 1 < len(matches) else len(history)
            turns.append(history[start:end].strip())
        return [turn for turn in turns if turn]

    def _speaker_from_text(self, text: str, speaker_agents: dict[str, str]) -> str | None:
        for speaker in speaker_agents:
            if text.startswith(f"{speaker}:"):
                return speaker
        return None

    def _speaker_from_latest_state(self, debate_state: dict[str, Any], latest_speaker_key: str | None, speaker_agents: dict[str, str]) -> str | None:
        if not latest_speaker_key:
            return None
        latest_speaker = str(debate_state.get(latest_speaker_key) or "")
        return latest_speaker if latest_speaker in speaker_agents else None

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
