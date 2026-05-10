"""Data vendor fallback tests for production web analysis reliability."""

from __future__ import annotations

import pytest
from yfinance.exceptions import YFRateLimitError


@pytest.mark.unit
def test_yfinance_stock_data_falls_back_to_sina_us_on_rate_limit(monkeypatch):
    """A Yahoo 429 should not abort market analysis when Sina has US OHLCV data."""

    from tradingagents.dataflows import y_finance

    class FakeTicker:
        def __init__(self, symbol: str):
            self.symbol = symbol

        def history(self, *args, **kwargs):
            raise YFRateLimitError()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"d": "2026-05-01", "o": "100.0", "h": "102.0", "l": "99.0", "c": "101.5", "v": "1000000"},
                {"d": "2026-05-04", "o": "101.0", "h": "103.0", "l": "100.0", "c": "102.5", "v": "1100000"},
            ]

    def fake_get(url, params, timeout, **kwargs):
        assert "stock.finance.sina.com.cn" in url
        assert params["symbol"] == "AAPL"
        return FakeResponse()

    monkeypatch.setattr(y_finance.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(y_finance, "yf_retry", lambda func: func())
    monkeypatch.setattr(y_finance._download_sina_ohlcv.__globals__["requests"], "get", fake_get)

    result = y_finance.get_YFin_data_online("AAPL", "2026-05-01", "2026-05-05")

    assert "# Stock data for AAPL from 2026-05-01 to 2026-05-05" in result
    assert "# Data source: Sina US fallback" in result
    assert "2026-05-04" in result
    assert "102.5" in result


@pytest.mark.unit
def test_yfinance_stock_data_falls_back_to_sina_cn_for_shanghai_ticker(monkeypatch):
    """A Yahoo 429 should not abort A-share analysis when Sina CN has OHLCV data."""

    from tradingagents.dataflows import y_finance

    class FakeTicker:
        def __init__(self, symbol: str):
            self.symbol = symbol

        def history(self, *args, **kwargs):
            raise YFRateLimitError()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"day": "2026-05-01", "open": "16.10", "high": "17.17", "low": "16.01", "close": "16.09", "volume": "133458031"},
                {"day": "2026-05-04", "open": "16.65", "high": "17.61", "low": "16.35", "close": "17.01", "volume": "159548977"},
            ]

    def fake_get(url, params, timeout, **kwargs):
        assert "CN_MarketData.getKLineData" in url
        assert params["symbol"] == "sh600330"
        return FakeResponse()

    monkeypatch.setattr(y_finance.yf, "Ticker", FakeTicker)
    monkeypatch.setattr(y_finance, "yf_retry", lambda func: func())
    monkeypatch.setattr(y_finance._download_sina_ohlcv.__globals__["requests"], "get", fake_get)

    result = y_finance.get_YFin_data_online("600330.SS", "2026-05-01", "2026-05-05")

    assert "# Stock data for 600330.SS from 2026-05-01 to 2026-05-05" in result
    assert "# Data source: Sina CN fallback" in result
    assert "2026-05-04" in result
    assert "17.01" in result


@pytest.mark.unit
def test_indicator_ohlcv_loader_falls_back_to_sina_us_on_rate_limit(monkeypatch, tmp_path):
    """Indicator calculation should keep working when Yahoo download is throttled."""

    from tradingagents.dataflows import stockstats_utils
    from tradingagents.dataflows.config import set_config

    def fake_download(*args, **kwargs):
        raise YFRateLimitError()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"d": "2026-05-01", "o": "100.0", "h": "102.0", "l": "99.0", "c": "101.5", "v": "1000000"},
                {"d": "2026-05-04", "o": "101.0", "h": "103.0", "l": "100.0", "c": "102.5", "v": "1100000"},
                {"d": "2026-05-06", "o": "104.0", "h": "105.0", "l": "103.0", "c": "104.5", "v": "1200000"},
            ]

    def fake_get(url, params, timeout, **kwargs):
        assert "stock.finance.sina.com.cn" in url
        assert params["symbol"] == "AAPL"
        return FakeResponse()

    set_config({"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(stockstats_utils.yf, "download", fake_download)
    monkeypatch.setattr(stockstats_utils, "yf_retry", lambda func: func())
    monkeypatch.setattr(stockstats_utils.requests, "get", fake_get)

    data = stockstats_utils.load_ohlcv("AAPL", "2026-05-05")

    assert list(data["Close"]) == [101.5, 102.5]
    assert data["Date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-05-01", "2026-05-04"]


@pytest.mark.unit
def test_indicator_ohlcv_loader_falls_back_when_yfinance_returns_empty(monkeypatch, tmp_path):
    """yfinance can log a failed download and return empty data instead of raising."""

    from tradingagents.dataflows import stockstats_utils
    from tradingagents.dataflows.config import set_config

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [
                {"d": "2026-05-01", "o": "100.0", "h": "102.0", "l": "99.0", "c": "101.5", "v": "1000000"},
                {"d": "2026-05-04", "o": "101.0", "h": "103.0", "l": "100.0", "c": "102.5", "v": "1100000"},
            ]

    set_config({"data_cache_dir": str(tmp_path)})
    monkeypatch.setattr(stockstats_utils.yf, "download", lambda *args, **kwargs: stockstats_utils.pd.DataFrame())
    monkeypatch.setattr(stockstats_utils.requests, "get", lambda *args, **kwargs: FakeResponse())

    data = stockstats_utils.load_ohlcv("AAPL", "2026-05-05")

    assert list(data["Close"]) == [101.5, 102.5]


@pytest.mark.unit
def test_indicator_window_does_not_call_missing_vendor_data_a_holiday(monkeypatch):
    """Missing vendor rows after the latest available date must not be reported as a market holiday."""

    from tradingagents.dataflows import y_finance

    monkeypatch.setattr(
        y_finance,
        "_get_stock_stats_bulk",
        lambda symbol, indicator, curr_date: {"2026-04-30": "27.89"},
    )

    result = y_finance.get_stock_stats_indicators_window("600330.SS", "close_10_ema", "2026-05-06", 6)

    assert "2026-05-06: N/A: Market data unavailable for this date; latest available trading date is 2026-04-30" in result
    assert "2026-05-06: N/A: Not a trading day" not in result
    assert "2026-04-30: 27.89" in result
