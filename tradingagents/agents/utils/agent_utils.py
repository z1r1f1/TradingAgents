from langchain_core.messages import HumanMessage, RemoveMessage

# Import tools from separate utility files
from tradingagents.agents.utils.core_stock_tools import (
    get_stock_data
)
from tradingagents.agents.utils.technical_indicators_tools import (
    get_indicators
)
from tradingagents.agents.utils.fundamental_data_tools import (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement
)
from tradingagents.agents.utils.news_data_tools import (
    get_news,
    get_insider_transactions,
    get_global_news
)


def get_language_instruction() -> str:
    """Return a strong prompt instruction for the configured output language.

    Returns empty string when English (default). For non-English output, this is
    intentionally strict because TradingAgents has many English base prompts and
    structured-output schemas; a weak one-sentence hint is easy for the model to
    ignore in later debate/manager stages.
    """
    from tradingagents.dataflows.config import get_config

    lang = get_config().get("output_language", "English")
    normalized = (lang or "English").strip().lower()
    if normalized == "english":
        return ""
    if normalized in {"chinese", "中文", "zh", "zh-cn", "simplified chinese", "简体中文"}:
        return (
            "\n\nIMPORTANT LANGUAGE REQUIREMENT: 必须使用简体中文撰写整份用户可见输出，"
            "包括摘要、分析、辩论观点、表格标题、结论和行动建议。"
            "除股票代码、公司名、工具名、字段名、数值单位以及 BUY/HOLD/SELL 等必要评级标记外，"
            "不要输出英文段落或英文解释。"
        )
    return (
        f"\n\nIMPORTANT LANGUAGE REQUIREMENT: Write the entire user-visible output in {lang}. "
        "This includes summaries, analysis, debate arguments, table headers, conclusions, and action recommendations. "
        "Only keep tickers, company names, tool names, field names, numeric units, and required rating markers in their original form."
    )


def build_instrument_context(ticker: str) -> str:
    """Describe the exact instrument so agents preserve exchange-qualified tickers."""
    return (
        f"The instrument to analyze is `{ticker}`. "
        "Use this exact ticker in every tool call, report, and recommendation, "
        "preserving any exchange suffix (e.g. `.TO`, `.L`, `.HK`, `.T`)."
    )

def create_msg_delete():
    def delete_messages(state):
        """Clear messages and add placeholder for Anthropic compatibility"""
        messages = state["messages"]

        # Remove all messages
        removal_operations = [RemoveMessage(id=m.id) for m in messages]

        # Add a minimal placeholder message
        placeholder = HumanMessage(content="Continue")

        return {"messages": removal_operations + [placeholder]}

    return delete_messages


        
