"""Tests for BCParksClient on_request callback and _summarize helper."""
from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from campcli.infrastructure.api import BCParksClient, _summarize
from campcli.domain.ports import ApiError, RateLimited


# ---- _summarize ------------------------------------------------------------

class TestSummarize:
    def test_empty_body(self):
        assert "0 chars" in _summarize("")

    def test_list_summary(self):
        body = '[{"id":1,"name":"a"},{"id":2,"name":"b"},{"id":3,"name":"c"}]'
        result = _summarize(body)
        assert "list[3]" in result

    def test_dict_summary(self):
        body = '{"foo":1,"bar":2,"baz":3}'
        result = _summarize(body)
        assert "dict(3 keys)" in result

    def test_non_json_preview(self):
        """Non-JSON body falls back to raw text preview."""
        body = "just plain text that is not json at all"
        result = _summarize(body)
        assert "chars" in result
        assert "just plain text" in result or "not json" in result

    def test_long_body_truncated(self):
        body = '{"data": "' + "x" * 500 + '"}'
        result = _summarize(body)
        assert "512 chars" in result
        assert "dict(1 keys)" in result  # JSON parsed → structured preview


# ---- on_request callback ---------------------------------------------------

def _mock_client(
    status: int = 200,
    body: str = "[]",
    json_return: object = None,
    network_error: bool = False,
) -> BCParksClient:
    mock_http = MagicMock(spec=httpx.Client)
    if network_error:
        mock_http.get.side_effect = httpx.HTTPError("connection refused")
    else:
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status
        resp.text = body
        resp.json.return_value = json_return if json_return is not None else []
        mock_http.get.return_value = resp
    return BCParksClient(client=mock_http, min_interval_secs=0)


class TestOnRequestCallback:
    def test_success_invokes_hook(self):
        calls: list[tuple] = []
        client = BCParksClient(
            client=MagicMock(spec=httpx.Client),
            min_interval_secs=0,
            on_request=lambda *a: calls.append(a),
        )
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.text = '[{"id":1}]'
        resp.json.return_value = [{"id": 1}]
        client._client.get.return_value = resp  # type: ignore[union-attr]

        client._get("/api/ping", params={"key": "val"})

        assert len(calls) == 1
        path, params, status, summary = calls[0]
        assert path == "/api/ping"
        assert params == {"key": "val"}
        assert status == 200
        assert "list[1]" in summary

    def test_403_invokes_hook_then_raises(self):
        calls: list[tuple] = []
        client = _mock_client(status=403)
        client._on_request = lambda *a: calls.append(a)

        with pytest.raises(RateLimited):
            client._get("/api/ping")

        assert len(calls) == 1
        assert calls[0][2] == 403
        assert "rate limited" in calls[0][3]

    def test_429_invokes_hook_then_raises(self):
        calls: list[tuple] = []
        client = _mock_client(status=429)
        client._on_request = lambda *a: calls.append(a)

        with pytest.raises(RateLimited):
            client._get("/api/ping")

        assert len(calls) == 1
        assert calls[0][2] == 429

    def test_500_invokes_hook_then_raises(self):
        calls: list[tuple] = []
        client = _mock_client(status=500, body="Internal Server Error")
        client._on_request = lambda *a: calls.append(a)

        with pytest.raises(ApiError):
            client._get("/api/ping")

        assert len(calls) == 1
        assert calls[0][2] == 500
        assert "Internal Server Error" in calls[0][3]

    def test_network_error_invokes_hook(self):
        calls: list[tuple] = []
        client = _mock_client(network_error=True)
        client._on_request = lambda *a: calls.append(a)

        with pytest.raises(ApiError):
            client._get("/api/ping")

        assert len(calls) == 1
        assert calls[0][2] == 0  # status=0 for network errors
        assert "network error" in calls[0][3]

    def test_no_hook_does_not_crash(self):
        client = _mock_client(status=200)
        client._on_request = None

        # Must not raise
        result = client._get("/api/ping")
        assert result == []

    def test_hook_receives_empty_params(self):
        calls: list[tuple] = []
        client = BCParksClient(
            client=MagicMock(spec=httpx.Client),
            min_interval_secs=0,
            on_request=lambda *a: calls.append(a),
        )
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.text = "{}"
        resp.json.return_value = {}
        client._client.get.return_value = resp  # type: ignore[union-attr]

        client._get("/api/ping")  # no params arg

        assert len(calls) == 1
        assert calls[0][1] == {}  # empty dict when params=None

    def test_constructor_hook_passed(self):
        """Verify the hook is wired through the constructor."""
        calls: list[tuple] = []
        client = _mock_client(status=200)
        client._on_request = None  # disconnect to test a separate path

        # Build a second client with the hook in __init__
        mock_http = MagicMock(spec=httpx.Client)
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.text = "[]"
        resp.json.return_value = []
        mock_http.get.return_value = resp

        client2 = BCParksClient(
            client=mock_http,
            min_interval_secs=0,
            on_request=lambda *a: calls.append(a),
        )
        client2._get("/api/test")

        assert len(calls) == 1
        assert calls[0][0] == "/api/test"
