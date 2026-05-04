"""Eastmoney-based A-share company news fetching functions."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import requests


_EASTMONEY_NEWS_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/NewsBulletin/PageAjax"
_A_SHARE_RE = re.compile(r"^(?P<code>\d{6})(?P<suffix>\.(?:SS|SH|SZ))?$", re.IGNORECASE)


class EastmoneyNoDataError(Exception):
    """Raised when Eastmoney cannot serve a symbol/date range."""


def _eastmoney_security_code(ticker: str) -> str | None:
    """Convert common A-share ticker forms to Eastmoney's SH/SZ code."""

    normalized = (ticker or "").strip().upper()
    match = _A_SHARE_RE.match(normalized)
    if not match:
        return None
    code = match.group("code")
    suffix = (match.group("suffix") or "").upper()
    if suffix in {".SS", ".SH"}:
        return f"SH{code}"
    if suffix == ".SZ":
        return f"SZ{code}"
    if code.startswith(("600", "601", "603", "605", "688", "689")):
        return f"SH{code}"
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return f"SZ{code}"
    return None


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _parse_datetime(value: Any) -> datetime | None:
    """Parse Eastmoney timestamp fields.

    PC_HSF10/PageAjax mixes millisecond integers for news (gszx) and strings like
    ``2026-04-30 17:21:40:592`` for announcements (gsgg).
    """

    if value is None:
        return None
    if isinstance(value, (int, float)):
        value_int = int(value)
        if value_int <= 0:
            return None
        return datetime.fromtimestamp(value_int / 1000)

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        value_int = int(text)
        if value_int <= 0:
            return None
        return datetime.fromtimestamp(value_int / 1000)

    for fmt in ("%Y-%m-%d %H:%M:%S:%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def get_news_eastmoney(ticker: str, start_date: str, end_date: str) -> str:
    """Retrieve A-share company news from Eastmoney.

    This is primarily for Shanghai/Shenzhen tickers such as 600330.SS, 600330.SH,
    000001.SZ, or bare six-digit A-share codes. Non-A-share symbols return a
    short no-data message so other configured vendors can be tried.
    """

    security_code = _eastmoney_security_code(ticker)
    if not security_code:
        raise EastmoneyNoDataError(f"No Eastmoney A-share news mapping for {ticker}")

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    # Include the full end date.
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)

    params = {
        "code": security_code,
        "pageSize": 50,
        "pageIndex": 1,
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/",
    }
    response = requests.get(_EASTMONEY_NEWS_URL, params=params, headers=headers, timeout=15)
    response.raise_for_status()
    payload = response.json()

    sections = []
    for section_name, section_payload in payload.items():
        if isinstance(section_payload, dict):
            data = section_payload.get("data", {})
            items = data.get("items", []) if isinstance(data, dict) else []
        elif isinstance(section_payload, list):
            items = section_payload
        else:
            items = []

        for item in items:
            if not isinstance(item, dict):
                continue
            published_at = _parse_datetime(
                item.get("showDateTime")
                or item.get("display_time")
                or item.get("publishDate")
                or item.get("notice_date")
                or item.get("updateTime")
            )
            if published_at and not (start_dt <= published_at <= end_dt):
                continue
            title = _safe_text(item.get("title"))
            if not title:
                continue
            summary = _safe_text(item.get("summary") or item.get("content"))
            if len(summary) > 500:
                summary = summary[:500].rstrip() + "..."
            url = _safe_text(item.get("uniqueUrl") or item.get("url"))
            if not url and item.get("art_code"):
                url = (
                    "https://data.eastmoney.com/notices/detail/"
                    f"{security_code[2:]}/{item['art_code']}.html"
                )
            source = _safe_text(item.get("source")) or ("东方财富公告" if section_name == "gsgg" else "东方财富")
            sections.append({
                "published_at": published_at,
                "title": title,
                "summary": summary,
                "url": url,
                "source": source,
            })

    # Newest first, de-duplicate by title.
    sections.sort(key=lambda x: x["published_at"] or datetime.min, reverse=True)
    deduped = []
    seen_titles = set()
    for item in sections:
        if item["title"] in seen_titles:
            continue
        seen_titles.add(item["title"])
        deduped.append(item)

    if not deduped:
        raise EastmoneyNoDataError(f"No Eastmoney news found for {ticker} between {start_date} and {end_date}")

    lines = [f"## {ticker} 东方财富相关新闻，{start_date} 至 {end_date}", ""]
    for item in deduped[:20]:
        date_str = item["published_at"].strftime("%Y-%m-%d %H:%M:%S") if item["published_at"] else "未知时间"
        lines.append(f"### {item['title']}（来源：{item['source']}，时间：{date_str}）")
        if item["summary"]:
            lines.append(item["summary"])
        if item["url"]:
            lines.append(f"链接: {item['url']}")
        lines.append("")
    return "\n".join(lines)
