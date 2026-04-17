"""Tests for TrainingPeaks auth configuration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from intervals_icu_mcp.auth import TPConfig, validate_tp_credentials
from intervals_icu_mcp.middleware import ConfigMiddleware


class TestTPConfig:
    def test_tp_config_loads_from_env(self, monkeypatch):
        """TPConfig reads TP_AUTH_COOKIE from environment."""
        monkeypatch.setenv("TP_AUTH_COOKIE", "test_cookie_value")
        config = TPConfig()
        assert config.tp_auth_cookie == "test_cookie_value"

    def test_validate_tp_credentials_valid(self):
        """Non-empty, non-placeholder cookie returns True."""
        config = TPConfig(tp_auth_cookie="some_real_cookie_abc123")
        assert validate_tp_credentials(config) is True

    def test_validate_tp_credentials_empty(self):
        """Empty cookie returns False."""
        config = TPConfig(tp_auth_cookie="")
        assert validate_tp_credentials(config) is False

    def test_validate_tp_credentials_placeholder(self):
        """Placeholder string returns False."""
        config = TPConfig(tp_auth_cookie="your_tp_cookie_here")
        assert validate_tp_credentials(config) is False


class TestConfigMiddlewareTP:
    @pytest.mark.asyncio
    async def test_middleware_injects_tp_config(self, monkeypatch):
        """ConfigMiddleware injects tp_config into context state alongside ICU config."""
        monkeypatch.setenv("INTERVALS_ICU_API_KEY", "test_api_key_12345")
        monkeypatch.setenv("INTERVALS_ICU_ATHLETE_ID", "i654321")
        monkeypatch.setenv("TP_AUTH_COOKIE", "test_tp_cookie_value")

        middleware = ConfigMiddleware()

        mock_ctx = MagicMock()
        mock_fastmcp_ctx = MagicMock()
        mock_ctx.fastmcp_context = mock_fastmcp_ctx

        states = {}
        mock_fastmcp_ctx.set_state.side_effect = lambda k, v: states.update({k: v})

        call_next = AsyncMock(return_value="result")
        await middleware.on_call_tool(mock_ctx, call_next)

        assert "tp_config" in states
        assert isinstance(states["tp_config"], TPConfig)
        assert states["tp_config"].tp_auth_cookie == "test_tp_cookie_value"

    @pytest.mark.asyncio
    async def test_middleware_injects_tp_config_when_absent(self, monkeypatch, tmp_path):
        """ConfigMiddleware injects tp_config even when TP cookie is not set (no ToolError)."""
        monkeypatch.chdir(tmp_path)  # isolate from any real .env in the repo
        monkeypatch.setenv("INTERVALS_ICU_API_KEY", "test_api_key_12345")
        monkeypatch.setenv("INTERVALS_ICU_ATHLETE_ID", "i654321")
        # setenv to "" (not delenv) so load_dotenv's override=False default won't
        # repopulate this value from the repo's real .env during the test.
        monkeypatch.setenv("TP_AUTH_COOKIE", "")

        middleware = ConfigMiddleware()

        mock_ctx = MagicMock()
        mock_fastmcp_ctx = MagicMock()
        mock_ctx.fastmcp_context = mock_fastmcp_ctx

        states = {}
        mock_fastmcp_ctx.set_state.side_effect = lambda k, v: states.update({k: v})

        call_next = AsyncMock(return_value="result")
        await middleware.on_call_tool(mock_ctx, call_next)

        assert "tp_config" in states
        assert isinstance(states["tp_config"], TPConfig)
        assert states["tp_config"].tp_auth_cookie == ""
