"""Regression tests for truncated daily responses and verified typhoon closure."""
from datetime import date
from unittest.mock import Mock
import requests
import pytest

from src import sources, historical


def test_daily_tpex_retries_truncated_response(monkeypatch):
    calls = []
    monkeypatch.setattr(sources.time, "sleep", lambda seconds: None)
    expected = [{"day": "2026-10-19", "market": "TPEX"}]

    def fake_get(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise requests.exceptions.ChunkedEncodingError("Response ended prematurely")
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"Date": "1151019"}]
        return response

    monkeypatch.setattr(sources.requests, "get", fake_get)
    monkeypatch.setattr(sources, "parse_snapshot", lambda rows, market: expected)
    assert sources.fetch_snapshot("TPEX") == expected
    assert len(calls) == 2


def test_daily_tpex_does_not_retry_bad_schema(monkeypatch):
    calls = []
    monkeypatch.setattr(sources.time, "sleep", lambda _: None)

    def fake_get(*args, **kwargs):
        calls.append(1)
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"unrecognized": "payload"}
        return response

    monkeypatch.setattr(sources.requests, "get", fake_get)
    with pytest.raises(ValueError):
        sources.fetch_snapshot("TPEX")
    assert len(calls) == 1


@pytest.mark.parametrize("market", ["TWSE", "TPEX"])
def test_verified_typhoon_date_never_requests_prices(market):
    session = Mock()
    with pytest.raises(historical.NoSessionData, match="official market holiday"):
        historical.fetch_historical_day(session, market, date(2026, 7, 10))
    session.get.assert_not_called()


def test_historical_client_retries_http_520():
    session = historical.client()
    adapter = session.get_adapter("https://www.tpex.org.tw")
    assert 520 in adapter.max_retries.status_forcelist
    session.close()


@pytest.mark.parametrize("market", ["TWSE", "TPEX"])
def test_2024_kong_rey_closure_is_not_schema_error(market):
    session = Mock()
    with pytest.raises(historical.NoSessionData, match="official market holiday"):
        historical.fetch_historical_day(session, market, date(2024, 10, 31))
    session.get.assert_not_called()
