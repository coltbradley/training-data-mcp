"""Middleware for Intervals.icu MCP server.

This module provides middleware components that run before tool execution.
"""

from collections.abc import Callable
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from .auth import load_config, load_tp_config, validate_credentials


class ConfigMiddleware(Middleware):
    """Middleware that loads and validates Intervals.icu configuration for all tool calls.

    This middleware:
    1. Loads the ICU config from environment variables
    2. Validates that credentials are properly configured
    3. Injects the config into the context state for tools to access via ctx.get_state("config")
    4. Also loads TPConfig and injects it as "tp_config" (absence does not raise ToolError)
    5. Raises ToolError if ICU authentication is not configured
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next: Callable[..., Any]):
        """Load and validate config before every tool call."""
        # Load ICU configuration from environment
        config = load_config()

        # Validate ICU credentials are properly configured
        if not validate_credentials(config):
            raise ToolError(
                "Intervals.icu credentials not configured. "
                "Please run 'icu-mcp-auth' to set up authentication."
            )

        # Load TP configuration (absence is not an error; TP tools handle their own auth)
        tp_config = load_tp_config()

        # Inject configs into context state for tools to access
        if context.fastmcp_context:
            context.fastmcp_context.set_state("config", config)
            context.fastmcp_context.set_state("tp_config", tp_config)

        # Continue to the tool execution
        return await call_next(context)
