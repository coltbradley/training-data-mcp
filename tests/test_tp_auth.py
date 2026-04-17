"""Tests for TrainingPeaks auth configuration."""

import os

import pytest

from intervals_icu_mcp.auth import TPConfig, load_tp_config, validate_tp_credentials


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
