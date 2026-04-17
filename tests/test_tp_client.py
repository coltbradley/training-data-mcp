"""Tests for TPClient and TPAPIError."""

import pytest
import respx
from httpx import Response

from intervals_icu_mcp.auth import TPConfig
from intervals_icu_mcp.client import TPAPIError, TPClient


@pytest.fixture
def tp_config():
    return TPConfig(tp_auth_cookie="test_cookie_value")


@pytest.fixture
def tp_respx_mock():
    with respx.mock(base_url="https://tpapi.trainingpeaks.com", assert_all_called=False) as m:
        yield m


class TestTPClient:
    async def test_client_sends_cookie_header(self, tp_config, tp_respx_mock):
        """TPClient sets the Production_tpAuth cookie header on requests."""
        route = tp_respx_mock.get("/test").mock(return_value=Response(200, json={"ok": True}))

        async with TPClient(tp_config) as client:
            response = await client.request("GET", "/test")

        assert response.status_code == 200
        sent_cookie = route.calls[0].request.headers.get("cookie", "")
        assert "Production_tpAuth=test_cookie_value" in sent_cookie

    async def test_client_raises_tp_api_error_on_401(self, tp_config, tp_respx_mock):
        """TPClient raises TPAPIError with a message mentioning 'cookie' on 401."""
        tp_respx_mock.get("/test").mock(return_value=Response(401))

        async with TPClient(tp_config) as client:
            with pytest.raises(TPAPIError) as exc_info:
                await client.request("GET", "/test")

        assert exc_info.value.status_code == 401
        assert "cookie" in exc_info.value.message.lower()

    async def test_client_raises_tp_api_error_on_404(self, tp_config, tp_respx_mock):
        """TPClient raises TPAPIError with status_code 404 on 404 responses."""
        tp_respx_mock.get("/missing").mock(return_value=Response(404))

        async with TPClient(tp_config) as client:
            with pytest.raises(TPAPIError) as exc_info:
                await client.request("GET", "/missing")

        assert exc_info.value.status_code == 404

    async def test_client_raises_tp_api_error_on_403(self, tp_config, tp_respx_mock):
        """TPClient raises TPAPIError with status_code 403 on 403 responses."""
        tp_respx_mock.get("/v1/test").mock(return_value=Response(403))

        async with TPClient(tp_config) as client:
            with pytest.raises(TPAPIError) as exc_info:
                await client.request("GET", "/v1/test")

        assert exc_info.value.status_code == 403
