"""Telegram delivery helpers for TradingAgents analysis outputs."""

from __future__ import annotations

import html
import os
import re
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from typing import Iterable

import requests


_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


def _env(name: str, fallback: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return fallback
    return value.strip()


def _telegram_config() -> tuple[str | None, str | None, bool]:
    token = _env("TRADINGAGENTS_TELEGRAM_BOT_TOKEN") or _env("TELEGRAM_BOT_TOKEN")
    chat_id = _env("TRADINGAGENTS_TELEGRAM_CHAT_ID") or _env("TELEGRAM_CHAT_ID")
    enabled_value = (_env("TRADINGAGENTS_TELEGRAM_ENABLED", "1") or "1").lower()
    enabled = enabled_value not in _FALSE_VALUES
    return token, chat_id, enabled


def _post_telegram(method: str, token: str, **kwargs) -> dict:
    url = f"https://api.telegram.org/bot{token}/{method}"
    timeout = int(os.getenv("TRADINGAGENTS_TELEGRAM_TIMEOUT", "60"))
    try:
        response = requests.post(url, timeout=timeout, **kwargs)
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        response = exc.response
        status_code = getattr(response, "status_code", "unknown")
        retry_after = None
        description = None
        if response is not None:
            try:
                payload = response.json()
                description = payload.get("description")
                retry_after = payload.get("parameters", {}).get("retry_after")
            except Exception:
                pass
        message = f"Telegram {method} failed with HTTP {status_code}"
        if description:
            message += f": {description}"
        if retry_after:
            message += f"; retry_after={retry_after}s"
        raise RuntimeError(message) from None
    except requests.RequestException as exc:
        raise RuntimeError(f"Telegram {method} request failed: {exc.__class__.__name__}") from None
    except ValueError:
        raise RuntimeError(f"Telegram {method} returned invalid JSON") from None

    if not payload.get("ok"):
        description = payload.get("description") or f"Telegram {method} failed"
        retry_after = payload.get("parameters", {}).get("retry_after")
        if retry_after:
            description = f"{description}; retry_after={retry_after}s"
        raise RuntimeError(description)
    return payload


def _send_message(token: str, chat_id: str, text: str) -> None:
    # Telegram text limit is 4096 chars. Keep this short and avoid parse_mode so
    # tickers/Markdown characters cannot break delivery.
    _post_telegram(
        "sendMessage",
        token,
        data={
            "chat_id": chat_id,
            "text": text[:3900],
            "disable_web_page_preview": "true",
        },
    )


def _render_inline_markdown_html(markdown_text: str) -> str:
    escaped = html.escape(markdown_text, quote=False)
    escaped = re.sub(r"(?m)^(#{1,6})\s+(.+)$", r"<b>\2</b>", escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped, flags=re.DOTALL)
    escaped = re.sub(r"__(.+?)__", r"<b>\1</b>", escaped, flags=re.DOTALL)
    escaped = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", escaped)
    return escaped


def _split_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_markdown_table_separator(line: str) -> bool:
    cells = _split_markdown_table_row(line)
    return len(cells) >= 2 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
    return width


def _pad_display(text: str, width: int) -> str:
    return text + " " * max(width - _display_width(text), 0)


def _format_markdown_table_as_pre(headers: list[str], rows: list[list[str]]) -> str:
    table_rows = [headers] + rows
    col_count = max(len(row) for row in table_rows)
    normalized = [row + [""] * (col_count - len(row)) for row in table_rows]
    widths = [max(_display_width(row[i]) for row in normalized) for i in range(col_count)]

    lines = []
    for index, row in enumerate(normalized):
        lines.append("  ".join(_pad_display(row[i], widths[i]) for i in range(col_count)).rstrip())
        if index == 0:
            lines.append("  ".join("-" * widths[i] for i in range(col_count)).rstrip())
    return f"<pre>{html.escape(chr(10).join(lines), quote=False)}</pre>"


def _format_markdown_table_as_cards(headers: list[str], rows: list[list[str]]) -> str:
    cards: list[str] = []
    for row in rows:
        normalized = row + [""] * max(len(headers) - len(row), 0)
        title = normalized[0] if normalized else "Row"
        card_lines = [f"<b>{html.escape(title, quote=False)}</b>"]
        for header, value in zip(headers[1:], normalized[1:]):
            if value:
                card_lines.append(
                    f"• {html.escape(header, quote=False)}：{html.escape(value, quote=False)}"
                )
        cards.append("\n".join(card_lines))
    return "\n\n".join(cards)


def _render_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    col_count = max([len(headers), *(len(row) for row in rows)] if rows else [len(headers)])
    pre_preview = _format_markdown_table_as_pre(headers, rows)
    pre_inner = re.sub(r"</?pre>", "", pre_preview)
    if col_count <= 4 and max((_display_width(line) for line in pre_inner.splitlines()), default=0) <= 72:
        return pre_preview
    return _format_markdown_table_as_cards(headers, rows)


def _consume_markdown_table(lines: list[str], start: int) -> tuple[str | None, int]:
    if start + 1 >= len(lines):
        return None, start
    if "|" not in lines[start] or not _is_markdown_table_separator(lines[start + 1]):
        return None, start

    headers = _split_markdown_table_row(lines[start])
    rows: list[list[str]] = []
    index = start + 2
    while index < len(lines) and "|" in lines[index].strip():
        row = _split_markdown_table_row(lines[index])
        if row and any(cell for cell in row):
            rows.append(row)
        index += 1
    if not rows:
        return None, start
    return _render_markdown_table(headers, rows), index


def _markdown_to_telegram_html(markdown_text: str) -> str:
    """Render common Markdown as Telegram-supported HTML safely.

    Hybrid table strategy:
    - small/narrow Markdown tables become <pre> fixed-width tables;
    - wide tables become mobile-friendly key/value cards.
    """
    lines = markdown_text.splitlines()
    output: list[str] = []
    plain_block: list[str] = []
    index = 0

    def flush_plain() -> None:
        if plain_block:
            output.append(_render_inline_markdown_html("\n".join(plain_block)))
            plain_block.clear()

    while index < len(lines):
        table_html, next_index = _consume_markdown_table(lines, index)
        if table_html is not None:
            flush_plain()
            output.append(table_html)
            index = next_index
            continue
        plain_block.append(lines[index])
        index += 1

    flush_plain()
    return "\n".join(output)


def _split_telegram_text(text: str, limit: int = 3500) -> list[str]:
    """Split text into Telegram-safe chunks, preferring paragraph boundaries."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks


def _send_markdown_message(token: str, chat_id: str, text: str) -> None:
    """Send Markdown report content as rendered Telegram messages, not files."""
    for markdown_chunk in _split_telegram_text(text):
        _post_telegram(
            "sendMessage",
            token,
            data={
                "chat_id": chat_id,
                "text": _markdown_to_telegram_html(markdown_chunk),
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            },
        )


def _send_document(token: str, chat_id: str, path: Path, caption: str | None = None) -> None:
    with path.open("rb") as file_obj:
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption[:1024]
        _post_telegram(
            "sendDocument",
            token,
            data=data,
            files={"document": (path.name, file_obj)},
        )


def _iter_report_files(report_dir: Path) -> Iterable[Path]:
    if not report_dir.exists():
        return []
    return sorted(path for path in report_dir.glob("*.md") if path.is_file())


def _create_bundle(ticker: str, analysis_date: str, report_dir: Path, log_file: Path) -> Path:
    safe_ticker = ticker.replace("/", "_").replace("\\", "_")
    bundle_path = Path(tempfile.gettempdir()) / f"tradingagents_{safe_ticker}_{analysis_date}_analysis_bundle.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for report_file in _iter_report_files(report_dir):
            zf.write(report_file, arcname=f"reports/{report_file.name}")
        if log_file.exists():
            zf.write(log_file, arcname="message_tool.log")
    return bundle_path


def _telegram_report_preview_chars() -> int:
    raw = _env("TRADINGAGENTS_TELEGRAM_REPORT_PREVIEW_CHARS", "1500") or "1500"
    try:
        value = int(raw)
    except ValueError:
        value = 1500
    return max(value, 100)


def _markdown_preview_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n_以上为内容预览；完整 Markdown 文件已随消息发送。_"


def maybe_send_report_to_telegram(
    *,
    ticker: str,
    analysis_date: str,
    report_path: Path,
    section_name: str,
) -> str | None:
    """Send one newly generated report file to Telegram when configured.

    Returns a short status string for CLI display, or None when Telegram delivery
    is not configured/enabled. Delivery failures raise exceptions so callers can
    treat them as non-fatal.
    """

    token, chat_id, enabled = _telegram_config()
    if not enabled or not token or not chat_id:
        return None
    if not report_path.exists() or not report_path.is_file():
        return None

    report_content = report_path.read_text(encoding="utf-8")
    preview_content = _markdown_preview_text(
        report_content,
        _telegram_report_preview_chars(),
    )
    message = (
        f"# TradingAgents Markdown 报告预览\n\n"
        f"**股票代码**: {ticker}\n"
        f"**分析日期**: {analysis_date}\n"
        f"**报告**: {section_name}\n"
        f"**文件**: {report_path.name}\n\n"
        f"---\n\n"
        f"{preview_content}"
    )
    _send_markdown_message(token, chat_id, message)
    _send_document(
        token,
        chat_id,
        report_path,
        caption=f"{ticker} {analysis_date} {report_path.name}",
    )
    return f"Telegram sent report preview and md file: {report_path.name}"



def maybe_send_analysis_to_telegram(
    *,
    ticker: str,
    analysis_date: str,
    results_dir: Path,
    report_dir: Path,
    log_file: Path,
    final_decision: str | None = None,
) -> str | None:
    """Send analysis artifacts to Telegram when configured.

    Returns a short status string for CLI display, or None when Telegram delivery
    is not configured/enabled. Delivery failures raise exceptions so callers can
    decide whether they should be fatal; the CLI treats them as non-fatal.
    """

    token, chat_id, enabled = _telegram_config()
    if not enabled or not token or not chat_id:
        return None

    report_files = list(_iter_report_files(report_dir))
    bundle_path = _create_bundle(ticker, analysis_date, report_dir, log_file)

    intro = (
        f"TradingAgents 分析完成\n"
        f"股票代码: {ticker}\n"
        f"分析日期: {analysis_date}\n"
        f"报告数量: {len(report_files)}\n"
        f"容器内目录: {results_dir}\n"
        f"已在每个 Markdown 报告生成时发送预览和 .md 文件；现在发送完整分析过程日志和全部报告压缩包。"
    )
    _send_message(token, chat_id, intro)

    _send_document(
        token,
        chat_id,
        bundle_path,
        caption=f"{ticker} {analysis_date} 完整分析过程和全部报告",
    )

    return f"Telegram sent: bundle ({len(report_files)} reports, log included={log_file.exists()})"
