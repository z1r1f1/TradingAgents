import time
import logging

import pandas as pd
import requests
import yfinance as yf
from yfinance.exceptions import YFRateLimitError
from stockstats import wrap
from typing import Annotated
import os
from .config import get_config
from .utils import safe_ticker_component

logger = logging.getLogger(__name__)


def _sina_us_symbol(symbol: str) -> str:
    """Return a Sina US-stock symbol for common ticker inputs."""
    safe_symbol = safe_ticker_component(symbol).upper()
    if safe_symbol.endswith(".US"):
        return safe_symbol[:-3]
    return safe_symbol


def _sina_cn_symbol(symbol: str) -> str:
    """Return a Sina CN stock symbol such as sh600330 or sz000001."""
    safe_symbol = safe_ticker_component(symbol).upper()
    if safe_symbol.endswith(".SS"):
        return f"sh{safe_symbol[:-3]}"
    if safe_symbol.endswith(".SZ"):
        return f"sz{safe_symbol[:-3]}"
    if safe_symbol.isdigit() and len(safe_symbol) == 6:
        prefix = "sh" if safe_symbol.startswith("6") else "sz"
        return f"{prefix}{safe_symbol}"
    raise RuntimeError(f"Symbol '{symbol}' is not a supported Sina CN ticker")


def _is_sina_cn_symbol(symbol: str) -> bool:
    safe_symbol = safe_ticker_component(symbol).upper()
    return safe_symbol.endswith((".SS", ".SZ")) or (safe_symbol.isdigit() and len(safe_symbol) == 6)


def _download_sina_us_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Download daily OHLCV data from Sina as a no-key Yahoo fallback."""
    response = requests.get(
        "https://stock.finance.sina.com.cn/usstock/api/json_v2.php/US_MinKService.getDailyK",
        params={"symbol": _sina_us_symbol(symbol)},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"No Sina US data found for symbol '{symbol}'")

    data = pd.DataFrame(
        {
            "Date": [item.get("d") for item in payload],
            "Open": [item.get("o") for item in payload],
            "High": [item.get("h") for item in payload],
            "Low": [item.get("l") for item in payload],
            "Close": [item.get("c") for item in payload],
            "Volume": [item.get("v") for item in payload],
        }
    )
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    in_window = data[(data["Date"] >= start_dt) & (data["Date"] <= end_dt)]
    if in_window.empty:
        in_window = data[data["Date"] <= end_dt].tail(60)
    data = in_window
    if data.empty:
        raise RuntimeError(f"No Sina US data found for symbol '{symbol}' between {start_date} and {end_date}")
    data["Date"] = data["Date"].dt.strftime("%Y-%m-%d")
    data.attrs["source"] = "Sina US fallback"
    return data


def _download_sina_cn_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Download daily OHLCV data from Sina CN as a no-key Yahoo fallback."""
    response = requests.get(
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
        params={"symbol": _sina_cn_symbol(symbol), "scale": 240, "ma": "no", "datalen": 6000},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"No Sina CN data found for symbol '{symbol}'")

    data = pd.DataFrame(
        {
            "Date": [item.get("day") for item in payload],
            "Open": [item.get("open") for item in payload],
            "High": [item.get("high") for item in payload],
            "Low": [item.get("low") for item in payload],
            "Close": [item.get("close") for item in payload],
            "Volume": [item.get("volume") for item in payload],
        }
    )
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    in_window = data[(data["Date"] >= start_dt) & (data["Date"] <= end_dt)]
    if in_window.empty:
        in_window = data[data["Date"] <= end_dt].tail(60)
    data = in_window
    if data.empty:
        raise RuntimeError(f"No Sina CN data found for symbol '{symbol}' between {start_date} and {end_date}")
    data["Date"] = data["Date"].dt.strftime("%Y-%m-%d")
    data.attrs["source"] = "Sina CN fallback"
    return data


def _download_sina_ohlcv(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Download daily OHLCV data from Sina for supported US/CN tickers."""
    if _is_sina_cn_symbol(symbol):
        return _download_sina_cn_ohlcv(symbol, start_date, end_date)
    return _download_sina_us_ohlcv(symbol, start_date, end_date)


def yf_retry(func, max_retries=3, base_delay=2.0):
    """Execute a yfinance call with exponential backoff on rate limits.

    yfinance raises YFRateLimitError on HTTP 429 responses but does not
    retry them internally. This wrapper adds retry logic specifically
    for rate limits. Other exceptions propagate immediately.
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except YFRateLimitError:
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Yahoo Finance rate limited, retrying in {delay:.0f}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                raise


def _clean_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize a stock DataFrame for stockstats: parse dates, drop invalid rows, fill price gaps."""
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data = data.dropna(subset=["Date"])

    price_cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in data.columns]
    data[price_cols] = data[price_cols].apply(pd.to_numeric, errors="coerce")
    data = data.dropna(subset=["Close"])
    data[price_cols] = data[price_cols].ffill().bfill()

    return data


def _has_ohlcv_rows(data: pd.DataFrame) -> bool:
    return not data.empty and {"Date", "Open", "High", "Low", "Close", "Volume"}.issubset(data.columns)


def missing_market_data_message(date_str: str, latest_date_str: str | None = None) -> str:
    """Return a precise message for a date with no OHLCV row.

    A missing row after the vendor's latest available date is a data freshness
    issue, not proof that the requested date was a market holiday.
    """
    if latest_date_str:
        try:
            requested = pd.to_datetime(date_str)
            latest = pd.to_datetime(latest_date_str)
        except Exception:
            requested = latest = None
        if requested is not None and latest is not None and requested > latest:
            return (
                "N/A: Market data unavailable for this date; "
                f"latest available trading date is {latest.strftime('%Y-%m-%d')}"
            )
    return "N/A: No market data row for this date (market holiday or vendor data gap)"


def _fetch_ohlcv_with_fallback(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    try:
        data = yf_retry(lambda: yf.download(
            symbol,
            start=start_date,
            end=end_date,
            multi_level_index=False,
            progress=False,
            auto_adjust=True,
        ))
        data = data.reset_index()
        if _has_ohlcv_rows(data):
            return data
        logger.warning("Yahoo Finance returned no OHLCV rows for %s; falling back to Sina data", symbol)
    except YFRateLimitError:
        logger.warning("Yahoo Finance rate limited for %s; falling back to Sina OHLCV data", symbol)
    return _download_sina_ohlcv(symbol, start_date, end_date)


def load_ohlcv(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch OHLCV data with caching, filtered to prevent look-ahead bias.

    Downloads 15 years of data up to today and caches per symbol. On
    subsequent calls the cache is reused. Rows after curr_date are
    filtered out so backtests never see future prices.
    """
    # Reject ticker values that would escape the cache directory when
    # interpolated into the cache filename (e.g. ``../../tmp/x``).
    safe_symbol = safe_ticker_component(symbol)

    config = get_config()
    curr_date_dt = pd.to_datetime(curr_date)

    # Cache uses a fixed window (15y to today) so one file per symbol
    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today_date.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{safe_symbol}-YFin-data-{start_str}-{end_str}.csv",
    )

    if os.path.exists(data_file):
        data = pd.read_csv(data_file, on_bad_lines="skip", encoding="utf-8")
        if not _has_ohlcv_rows(data):
            logger.warning("Cached OHLCV data for %s is empty or invalid; refreshing from fallback sources", symbol)
            data = _fetch_ohlcv_with_fallback(symbol, start_str, end_str)
            data.to_csv(data_file, index=False, encoding="utf-8")
    else:
        data = _fetch_ohlcv_with_fallback(symbol, start_str, end_str)
        data.to_csv(data_file, index=False, encoding="utf-8")

    data = _clean_dataframe(data)

    # Filter to curr_date to prevent look-ahead bias in backtesting
    data = data[data["Date"] <= curr_date_dt]

    return data


def filter_financials_by_date(data: pd.DataFrame, curr_date: str) -> pd.DataFrame:
    """Drop financial statement columns (fiscal period timestamps) after curr_date.

    yfinance financial statements use fiscal period end dates as columns.
    Columns after curr_date represent future data and are removed to
    prevent look-ahead bias.
    """
    if not curr_date or data.empty:
        return data
    cutoff = pd.Timestamp(curr_date)
    mask = pd.to_datetime(data.columns, errors="coerce") <= cutoff
    return data.loc[:, mask]


class StockstatsUtils:
    @staticmethod
    def get_stock_stats(
        symbol: Annotated[str, "ticker symbol for the company"],
        indicator: Annotated[
            str, "quantitative indicators based off of the stock data for the company"
        ],
        curr_date: Annotated[
            str, "curr date for retrieving stock price data, YYYY-mm-dd"
        ],
    ):
        data = load_ohlcv(symbol, curr_date)
        df = wrap(data)
        df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
        curr_date_str = pd.to_datetime(curr_date).strftime("%Y-%m-%d")

        df[indicator]  # trigger stockstats to calculate the indicator
        matching_rows = df[df["Date"].str.startswith(curr_date_str)]

        if not matching_rows.empty:
            indicator_value = matching_rows[indicator].values[0]
            return indicator_value
        else:
            latest_date = df["Date"].max() if not df.empty else None
            return missing_market_data_message(curr_date_str, latest_date)
