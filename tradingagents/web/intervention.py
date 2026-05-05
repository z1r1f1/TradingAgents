from __future__ import annotations

from typing import Any

from .database import WebRepository

AGENT_SECTION_MAP = {
    "Market Analyst": "market_report",
    "Social Analyst": "sentiment_report",
    "News Analyst": "news_report",
    "Fundamentals Analyst": "fundamentals_report",
    "Research Manager": "investment_plan",
    "Trader": "trader_investment_plan",
    "Portfolio Manager": "final_trade_decision",
}


class InterventionService:
    def __init__(self, repository: WebRepository, *, max_context_chars: int = 4000):
        self.repository = repository
        self.max_context_chars = max_context_chars

    def run_continuation(self, session_id: int, user_id: int) -> dict[str, Any] | None:
        session = self.repository.get_intervention_for_user(session_id, user_id)
        if not session or session["status"] != "open":
            return None
        self.repository.append_intervention_event(session_id, "continuation.started", "Continuation started")
        context = self._build_context(session, user_id)
        content = self._generate_deterministic_output(session, context)
        output = self.repository.create_intervention_output(
            session_id,
            target_agent_name=session["target_agent_name"],
            content=content,
            context={"bounded_context": context},
        )
        self.repository.append_intervention_event(session_id, "continuation.completed", "Continuation completed")
        return output

    def _build_context(self, session: dict[str, Any], user_id: int) -> str:
        task = self.repository.get_task_for_user(session["source_analysis_task_id"], user_id)
        if not task:
            return ""
        section_name = AGENT_SECTION_MAP.get(session["target_agent_name"])
        original = ""
        for section in task.get("report_sections", []):
            if section["section_name"] == section_name:
                original = section["content"]
                break
        guidance = "\n".join(message["content"] for message in session.get("messages", []) if message["author"] == "user")
        memories = task.get("attached_memories", [])
        memory_text = "\n".join(f"{memory['agent_name']} {memory['ticker']} {memory['analysis_date']}: {memory['content']}" for memory in memories)
        context = (
            f"Source task: {task['id']}\n"
            f"Target agent: {session['target_agent_name']}\n"
            f"Original output:\n{original}\n\n"
            f"User guidance:\n{guidance}\n\n"
            f"Attached memories ({len(memories)}):\n{memory_text}"
        )
        return context[: self.max_context_chars]

    def _generate_deterministic_output(self, session: dict[str, Any], context: str) -> str:
        guidance = "\n".join(message["content"] for message in session.get("messages", []) if message["author"] == "user")
        memory_count = context.split("Attached memories (", 1)[1].split(")", 1)[0] if "Attached memories (" in context else "0"
        return (
            f"Human-guided continuation for {session['target_agent_name']}.\n"
            f"Guidance: {guidance or 'No explicit guidance provided.'}\n"
            f"Attached memories: {memory_count}\n"
            "This continuation is stored separately from the original analysis report."
        )
