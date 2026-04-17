# TrainingPeaks integration implementation plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 6 TrainingPeaks tools (planned workouts, compliance, calendar, workout details, athlete metrics, auth check) to the existing intervals-icu-mcp FastMCP server.

**Architecture:** Extend auth.py with `TPConfig`, extend middleware to inject `tp_config` into context state alongside the existing `config`, add `TPClient` to client.py using cookie-based auth, and implement 6 tools in a new `tools/trainingpeaks.py` following the exact same async pattern as existing tools.

**Tech Stack:** FastMCP, httpx, pydantic-settings, python-dotenv. No new dependencies needed.

**Reference repo:** https://github.com/JamsusMaximus/trainingpeaks-mcp — consult for exact TP API endpoint paths and response shapes before implementing each tool.

---

### Task 1: Add TPConfig to auth.py

**Files:**

- Modify: `src/intervals_icu_mcp/auth.py`

**Step 1: Write the failing test**

Create `tests/test_tp_auth.py`:

```python
"""Tests for TrainingPeaks auth config."""

import pytest
from intervals_icu_mcp.auth import TPConfig, validate_tp_credentials


class TestTPConfig:
    def test_tp_config_loads_from_env(self, monkeypatch):
        monkeypatch.setenv("TP_AUTH_COOKIE", "test_cookie_value")
        config = TPConfig()
        assert config.tp_auth_cookie == "test_cookie_value"

    def test_validate_tp_credentials_valid(self):
        config = TPConfig(tp_auth_cookie="real_cookie")
        assert validate_tp_credentials(config) is True

    def test_validate_tp_credentials_empty(self):
        config = TPConfig(tp_auth_cookie="")
        assert validate_tp_credentials(config) is False

    def test_validate_tp_credentials_placeholder(self):
        config = TPConfig(tp_auth_cookie="your_tp_cookie_here")
        assert validate_tp_credentials(config) is False
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_tp_auth.py -v
```

Expected: FAIL — `TPConfig` and `validate_tp_credentials` not yet defined.

**Step 3: Implement**

Add to `src/intervals_icu_mcp/auth.py` after the existing `ICUConfig` class:

```python
class TPConfig(BaseSettings):
    """TrainingPeaks configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    tp_auth_cookie: str = ""


def load_tp_config() -> TPConfig:
    """Load TrainingPeaks configuration from .env file."""
    load_dotenv()
    return TPConfig()


def validate_tp_credentials(config: TPConfig) -> bool:
    """Check if TrainingPeaks credentials are configured."""
    if not config.tp_auth_cookie or config.tp_auth_cookie == "your_tp_cookie_here":
        return False
    return True


def update_tp_env_key(cookie: str) -> None:
    """Save the TrainingPeaks auth cookie to .env."""
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        env_path.touch()
    set_key(str(env_path), "TP_AUTH_COOKIE", cookie)
    os.environ["TP_AUTH_COOKIE"] = cookie
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_tp_auth.py -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_tp_auth.py src/intervals_icu_mcp/auth.py
git commit -m "feat: add TPConfig and credential helpers to auth.py"
```

---

### Task 2: Extend ConfigMiddleware to inject tp_config

**Files:**

- Modify: `src/intervals_icu_mcp/middleware.py`

**Step 1: Write the failing test**

Add to `tests/test_tp_auth.py`:

```python
import json
from unittest.mock import AsyncMock, MagicMock
from intervals_icu_mcp.middleware import ConfigMiddleware
from intervals_icu_mcp.auth import ICUConfig, TPConfig


class TestConfigMiddlewareTP:
    async def test_middleware_injects_tp_config(self, monkeypatch):
        monkeypatch.setenv("INTERVALS_ICU_API_KEY", "test_key")
        monkeypatch.setenv("INTERVALS_ICU_ATHLETE_ID", "i123456")
        monkeypatch.setenv("TP_AUTH_COOKIE", "test_cookie")

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
        assert states["tp_config"].tp_auth_cookie == "test_cookie"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_tp_auth.py::TestConfigMiddlewareTP -v
```

Expected: FAIL — middleware doesn't inject `tp_config` yet.

**Step 3: Implement**

Update `src/intervals_icu_mcp/middleware.py`:

```python
"""Middleware for Intervals.icu MCP server."""

from collections.abc import Callable
from typing import Any

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext

from .auth import load_config, load_tp_config, validate_credentials


class ConfigMiddleware(Middleware):
    """Middleware that loads and validates configuration for all tool calls.

    Injects ICU config as ctx state key "config" and TP config as "tp_config".
    Raises ToolError if Intervals.icu credentials are not configured.
    TP credentials are optional — TP tools return their own error if missing.
    """

    async def on_call_tool(self, context: MiddlewareContext, call_next: Callable[..., Any]):
        """Load and validate config before every tool call."""
        config = load_config()

        if not validate_credentials(config):
            raise ToolError(
                "Intervals.icu credentials not configured. "
                "Please run 'intervals-icu-mcp-auth' to set up authentication."
            )

        tp_config = load_tp_config()

        if context.fastmcp_context:
            context.fastmcp_context.set_state("config", config)
            context.fastmcp_context.set_state("tp_config", tp_config)

        return await call_next(context)
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_tp_auth.py -v
```

Expected: all PASS

**Step 5: Commit**

```bash
git add src/intervals_icu_mcp/middleware.py tests/test_tp_auth.py
git commit -m "feat: inject tp_config into middleware context state"
```

---

### Task 3: Add TPClient to client.py

**Files:**

- Modify: `src/intervals_icu_mcp/client.py`

**Step 1: Write the failing test**

Create `tests/test_tp_client.py`:

```python
"""Tests for TrainingPeaks HTTP client."""

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
        tp_respx_mock.get("/v1/athlete/self").mock(
            return_value=Response(200, json={"userId": 42, "username": "colt"})
        )
        async with TPClient(tp_config) as client:
            response = await client._request("GET", "/v1/athlete/self")
        assert response.status_code == 200

    async def test_client_raises_tp_api_error_on_401(self, tp_config, tp_respx_mock):
        tp_respx_mock.get("/v1/athlete/self").mock(return_value=Response(401))
        async with TPClient(tp_config) as client:
            with pytest.raises(TPAPIError) as exc_info:
                await client._request("GET", "/v1/athlete/self")
        assert "cookie" in exc_info.value.message.lower()
        assert exc_info.value.status_code == 401

    async def test_client_raises_tp_api_error_on_404(self, tp_config, tp_respx_mock):
        tp_respx_mock.get("/v1/workouts/999").mock(return_value=Response(404))
        async with TPClient(tp_config) as client:
            with pytest.raises(TPAPIError):
                await client._request("GET", "/v1/workouts/999")
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_tp_client.py -v
```

Expected: FAIL — `TPClient` and `TPAPIError` not yet defined.

**Step 3: Implement**

Add to the bottom of `src/intervals_icu_mcp/client.py`:

```python
class TPAPIError(Exception):
    """Custom exception for TrainingPeaks API errors."""

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class TPClient:
    """Async HTTP client for the TrainingPeaks API using cookie-based auth."""

    BASE_URL = "https://tpapi.trainingpeaks.com"

    def __init__(self, config: "TPConfig"):  # noqa: F821 — imported at runtime
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "TPClient":
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=30.0,
            headers={"Cookie": f"Production_tpAuth={self.config.tp_auth_cookie}"},
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        if self._client:
            await self._client.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> httpx.Response:
        if not self._client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        try:
            response = await self._client.request(method, endpoint, **kwargs)

            if response.status_code == 401:
                raise TPAPIError(
                    "TrainingPeaks cookie expired or invalid. "
                    "Re-run 'intervals-icu-mcp-auth' and paste a fresh Production_tpAuth cookie "
                    "(DevTools → Application → Cookies → trainingpeaks.com).",
                    401,
                )
            if response.status_code == 403:
                raise TPAPIError(
                    "TrainingPeaks access denied. Your cookie may have expired.",
                    403,
                )
            if response.status_code == 404:
                raise TPAPIError("TrainingPeaks resource not found.", 404)
            if response.status_code == 429:
                raise TPAPIError("TrainingPeaks rate limit exceeded. Try again later.", 429)

            response.raise_for_status()
            return response

        except httpx.HTTPStatusError as e:
            raise TPAPIError(
                f"HTTP {e.response.status_code}: {e.response.text}",
                e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise TPAPIError(f"Request failed: {str(e)}") from e
```

Note: `TPConfig` is imported at the top of `client.py` by adding it to the existing import:

```python
from .auth import ICUConfig, TPConfig
```

**Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_tp_client.py -v
```

Expected: all PASS

**Step 5: Commit**

```bash
git add src/intervals_icu_mcp/client.py tests/test_tp_client.py
git commit -m "feat: add TPClient and TPAPIError to client.py"
```

---

### Task 4: Implement tools/trainingpeaks.py

**Files:**

- Create: `src/intervals_icu_mcp/tools/trainingpeaks.py`

Before writing code, open the reference repo and find the exact endpoint paths for each tool:

- https://github.com/JamsusMaximus/trainingpeaks-mcp — look in `tools/` and `client/` directories
- Note the athlete user ID (different from Intervals athlete ID — it's a numeric TP user ID returned from the athlete profile endpoint)

**Step 1: Write the failing tests**

Create `tests/test_tp_tools.py`:

```python
"""Tests for TrainingPeaks tools."""

import json
from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response

from intervals_icu_mcp.auth import TPConfig
from intervals_icu_mcp.tools.trainingpeaks import (
    tp_check_auth,
    tp_get_athlete_metrics,
    tp_get_calendar,
    tp_get_compliance,
    tp_get_planned_workouts,
    tp_get_workout_details,
)


@pytest.fixture
def tp_config():
    return TPConfig(tp_auth_cookie="test_cookie")


@pytest.fixture
def mock_tp_ctx(tp_config):
    ctx = MagicMock()
    ctx.get_state.side_effect = lambda k: tp_config if k == "tp_config" else None
    return ctx


@pytest.fixture
def tp_respx_mock():
    with respx.mock(base_url="https://tpapi.trainingpeaks.com", assert_all_called=False) as m:
        yield m


class TestTPCheckAuth:
    async def test_returns_valid_when_cookie_works(self, mock_tp_ctx, tp_respx_mock):
        # Replace /v1/athlete/self with the actual TP auth-check endpoint from the reference repo
        tp_respx_mock.get("/v1/athlete/self").mock(
            return_value=Response(200, json={"userId": 42, "username": "colt"})
        )
        result = await tp_check_auth(ctx=mock_tp_ctx)
        response = json.loads(result)
        assert "data" in response
        assert response["data"]["authenticated"] is True

    async def test_returns_error_when_cookie_invalid(self, mock_tp_ctx, tp_respx_mock):
        tp_respx_mock.get("/v1/athlete/self").mock(return_value=Response(401))
        result = await tp_check_auth(ctx=mock_tp_ctx)
        response = json.loads(result)
        assert "error" in response


class TestTPGetPlannedWorkouts:
    async def test_returns_planned_workouts(self, mock_tp_ctx, tp_respx_mock):
        # Replace endpoint path with actual from reference repo
        tp_respx_mock.get("/v1/athlete/self").mock(
            return_value=Response(200, json={"userId": 42})
        )
        tp_respx_mock.get("/v1/workouts/2026-04-14/2026-04-20").mock(
            return_value=Response(200, json=[
                {"workoutId": 1, "workoutDay": "2026-04-15", "title": "Zone 2 Run",
                 "workoutTypeValueId": 3, "totalTimePlanned": 3600}
            ])
        )
        result = await tp_get_planned_workouts(
            start_date="2026-04-14", end_date="2026-04-20", ctx=mock_tp_ctx
        )
        response = json.loads(result)
        assert "data" in response
        assert len(response["data"]["workouts"]) == 1

    async def test_missing_tp_credentials_returns_error(self):
        ctx = MagicMock()
        ctx.get_state.side_effect = lambda k: TPConfig(tp_auth_cookie="") if k == "tp_config" else None
        result = await tp_get_planned_workouts(
            start_date="2026-04-14", end_date="2026-04-20", ctx=ctx
        )
        response = json.loads(result)
        assert "error" in response
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_tp_tools.py -v
```

Expected: FAIL — module not yet created.

**Step 3: Implement**

Consult the reference repo for exact endpoint paths. The pattern below uses placeholder paths — replace with actuals.

Create `src/intervals_icu_mcp/tools/trainingpeaks.py`:

```python
"""TrainingPeaks tools for intervals-icu-mcp server."""

from typing import Any

from fastmcp import Context

from ..auth import TPConfig, validate_tp_credentials
from ..client import TPAPIError, TPClient
from ..response_builder import ResponseBuilder


def _require_tp_config(ctx: Context) -> TPConfig | None:
    """Get TP config from context, returning None if not configured."""
    config: TPConfig = ctx.get_state("tp_config")
    if not validate_tp_credentials(config):
        return None
    return config


_TP_NOT_CONFIGURED = ResponseBuilder.build_error_response(
    "TrainingPeaks credentials not configured. "
    "Run 'intervals-icu-mcp-auth' and follow the TrainingPeaks setup steps.",
    error_type="auth_error",
    suggestions=[
        "Open DevTools in your browser while logged into TrainingPeaks",
        "Go to Application → Cookies → trainingpeaks.com",
        "Copy the value of Production_tpAuth",
        "Re-run intervals-icu-mcp-auth and paste it when prompted",
    ],
)


async def tp_check_auth(
    ctx: Context | None = None,
) -> str:
    """Check if the TrainingPeaks cookie is valid and return basic athlete info.

    Use this to verify TrainingPeaks authentication is working before using other TP tools.

    Returns:
        JSON with authentication status and athlete username
    """
    assert ctx is not None
    config = _require_tp_config(ctx)
    if not config:
        return _TP_NOT_CONFIGURED

    try:
        async with TPClient(config) as client:
            # Consult reference repo for exact endpoint
            response = await client._request("GET", "/v1/athlete/self")
            athlete = response.json()
            return ResponseBuilder.build_response(
                data={
                    "authenticated": True,
                    "user_id": athlete.get("userId"),
                    "username": athlete.get("username"),
                },
                query_type="tp_auth_check",
            )
    except TPAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="auth_error")


async def tp_get_planned_workouts(
    start_date: str,
    end_date: str,
    ctx: Context | None = None,
) -> str:
    """Get workouts planned by your coach in TrainingPeaks for a date range.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        JSON with list of planned workouts including targets and descriptions
    """
    assert ctx is not None
    config = _require_tp_config(ctx)
    if not config:
        return _TP_NOT_CONFIGURED

    try:
        async with TPClient(config) as client:
            # Get user ID first (consult reference repo for caching approach if needed)
            athlete_resp = await client._request("GET", "/v1/athlete/self")
            user_id = athlete_resp.json().get("userId")

            # Consult reference repo for exact workouts endpoint path
            workouts_resp = await client._request(
                "GET", f"/v1/workouts/{start_date}/{end_date}"
            )
            workouts = workouts_resp.json()

            planned = []
            for w in workouts:
                workout: dict[str, Any] = {
                    "workout_id": w.get("workoutId"),
                    "date": w.get("workoutDay"),
                    "title": w.get("title"),
                    "sport": w.get("workoutTypeValueId"),  # map to name if reference repo has mapping
                    "description": w.get("description"),
                    "planned_duration_secs": w.get("totalTimePlanned"),
                    "planned_distance_meters": w.get("totalDistancePlanned"),
                    "planned_tss": w.get("tssPlanned"),
                }
                planned.append(workout)

            return ResponseBuilder.build_response(
                data={"workouts": planned, "count": len(planned)},
                metadata={"start_date": start_date, "end_date": end_date},
                query_type="tp_planned_workouts",
            )
    except TPAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")


async def tp_get_workout_details(
    workout_id: str,
    ctx: Context | None = None,
) -> str:
    """Get detailed targets and structure for a specific TrainingPeaks workout.

    Use this after tp_get_planned_workouts to see the exact intervals, power zones,
    HR targets, and step-by-step structure your coach set.

    Args:
        workout_id: The workout ID from tp_get_planned_workouts

    Returns:
        JSON with full workout structure including zone targets and step descriptions
    """
    assert ctx is not None
    config = _require_tp_config(ctx)
    if not config:
        return _TP_NOT_CONFIGURED

    try:
        async with TPClient(config) as client:
            # Consult reference repo for exact endpoint path
            response = await client._request("GET", f"/v1/workouts/{workout_id}")
            w = response.json()

            return ResponseBuilder.build_response(
                data={
                    "workout_id": w.get("workoutId"),
                    "title": w.get("title"),
                    "date": w.get("workoutDay"),
                    "description": w.get("description"),
                    "coach_comments": w.get("coachComments"),
                    "planned_duration_secs": w.get("totalTimePlanned"),
                    "planned_distance_meters": w.get("totalDistancePlanned"),
                    "planned_tss": w.get("tssPlanned"),
                    "structure": w.get("structure"),  # structured workout steps if present
                },
                query_type="tp_workout_details",
            )
    except TPAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")


async def tp_get_compliance(
    start_date: str,
    end_date: str,
    ctx: Context | None = None,
) -> str:
    """Get workout compliance data — how well completed workouts matched targets.

    Returns planned vs actual metrics for each workout in the date range.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        JSON with planned vs actual comparison for each workout
    """
    assert ctx is not None
    config = _require_tp_config(ctx)
    if not config:
        return _TP_NOT_CONFIGURED

    try:
        async with TPClient(config) as client:
            # Consult reference repo for exact endpoint — may be same workouts endpoint
            # with both planned and actual fields, or a separate compliance endpoint
            response = await client._request(
                "GET", f"/v1/workouts/{start_date}/{end_date}"
            )
            workouts = response.json()

            compliance_data = []
            for w in workouts:
                # Only include workouts that have both planned and actual data
                if w.get("totalTimePlanned") and w.get("totalTime"):
                    compliance_data.append({
                        "workout_id": w.get("workoutId"),
                        "date": w.get("workoutDay"),
                        "title": w.get("title"),
                        "planned_duration_secs": w.get("totalTimePlanned"),
                        "actual_duration_secs": w.get("totalTime"),
                        "planned_tss": w.get("tssPlanned"),
                        "actual_tss": w.get("tss"),
                        "planned_distance_meters": w.get("totalDistancePlanned"),
                        "actual_distance_meters": w.get("totalDistance"),
                        "compliance_code": w.get("complianceCode"),  # TP's own compliance flag
                    })

            return ResponseBuilder.build_response(
                data={"compliance": compliance_data, "count": len(compliance_data)},
                metadata={"start_date": start_date, "end_date": end_date},
                query_type="tp_compliance",
            )
    except TPAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")


async def tp_get_calendar(
    start_date: str,
    end_date: str,
    ctx: Context | None = None,
) -> str:
    """Get full TrainingPeaks calendar including planned workouts and notes.

    Returns all calendar items (workouts, notes, events) for the date range.
    Useful for seeing the full coaching picture for a week.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        JSON with all calendar items grouped by date
    """
    assert ctx is not None
    config = _require_tp_config(ctx)
    if not config:
        return _TP_NOT_CONFIGURED

    try:
        async with TPClient(config) as client:
            # Consult reference repo — may be same workouts endpoint or a dedicated calendar endpoint
            response = await client._request(
                "GET", f"/v1/workouts/{start_date}/{end_date}"
            )
            items = response.json()

            # Group by date
            by_date: dict[str, list[dict[str, Any]]] = {}
            for item in items:
                date = item.get("workoutDay", "unknown")
                if date not in by_date:
                    by_date[date] = []
                by_date[date].append({
                    "id": item.get("workoutId"),
                    "title": item.get("title"),
                    "sport": item.get("workoutTypeValueId"),
                    "planned_duration_secs": item.get("totalTimePlanned"),
                    "completed": item.get("completed", False),
                    "tss_planned": item.get("tssPlanned"),
                    "tss_actual": item.get("tss"),
                })

            return ResponseBuilder.build_response(
                data={"calendar": by_date, "total_items": len(items)},
                metadata={"start_date": start_date, "end_date": end_date},
                query_type="tp_calendar",
            )
    except TPAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")


async def tp_get_athlete_metrics(
    ctx: Context | None = None,
) -> str:
    """Get TrainingPeaks fitness metrics (ATL, CTL, TSB).

    Returns TrainingPeaks' own training load numbers. Compare with Intervals.icu's
    get_fitness_summary to see if the platforms agree on your current form.

    Returns:
        JSON with TP fitness metrics
    """
    assert ctx is not None
    config = _require_tp_config(ctx)
    if not config:
        return _TP_NOT_CONFIGURED

    try:
        async with TPClient(config) as client:
            # Consult reference repo for exact metrics endpoint
            athlete_resp = await client._request("GET", "/v1/athlete/self")
            athlete = athlete_resp.json()
            user_id = athlete.get("userId")

            # Consult reference repo for fitness/metrics endpoint path
            metrics_resp = await client._request("GET", f"/fitness/v6/athletes/{user_id}/fitness")
            metrics = metrics_resp.json()

            return ResponseBuilder.build_response(
                data={
                    "atl": metrics.get("atl"),
                    "ctl": metrics.get("ctl"),
                    "tsb": metrics.get("tsb"),
                    "ramp_rate": metrics.get("rampRate"),
                },
                query_type="tp_athlete_metrics",
            )
    except TPAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_tp_tools.py -v
```

Expected: all PASS. If endpoint paths in tests don't match implementation, align them.

**Step 5: Commit**

```bash
git add src/intervals_icu_mcp/tools/trainingpeaks.py tests/test_tp_tools.py
git commit -m "feat: implement 6 TrainingPeaks tools"
```

---

### Task 5: Register TP tools in server.py

**Files:**

- Modify: `src/intervals_icu_mcp/server.py`

**Step 1: No test needed** — registration failures surface immediately on server start.

**Step 2: Implement**

Add to `src/intervals_icu_mcp/server.py` after the existing tool imports (around line 70):

```python
from .tools.trainingpeaks import (
    tp_check_auth,
    tp_get_athlete_metrics,
    tp_get_calendar,
    tp_get_compliance,
    tp_get_planned_workouts,
    tp_get_workout_details,
)
```

And after the existing `mcp.tool()` registrations (around line 135):

```python
# Register TrainingPeaks tools
mcp.tool()(tp_check_auth)
mcp.tool()(tp_get_planned_workouts)
mcp.tool()(tp_get_workout_details)
mcp.tool()(tp_get_compliance)
mcp.tool()(tp_get_calendar)
mcp.tool()(tp_get_athlete_metrics)
```

**Step 3: Smoke test**

```bash
uv run intervals-icu-mcp --help
```

Expected: no import errors. If it errors, check the import path.

**Step 4: Run full test suite**

```bash
uv run pytest -v
```

Expected: all existing tests still pass.

**Step 5: Commit**

```bash
git add src/intervals_icu_mcp/server.py
git commit -m "feat: register TrainingPeaks tools with FastMCP server"
```

---

### Task 6: Update .env.example and extend setup_auth.py

**Files:**

- Modify: `.env.example`
- Modify: `src/intervals_icu_mcp/scripts/setup_auth.py`

**Step 1: Update .env.example**

Add to `.env.example`:

```bash
# TrainingPeaks Authentication
# Your Production_tpAuth session cookie from trainingpeaks.com
# To find it: DevTools (F12) → Application → Cookies → trainingpeaks.com → Production_tpAuth
# Note: This cookie expires periodically. Re-run 'intervals-icu-mcp-auth' when TP tools stop working.
TP_AUTH_COOKIE=your_tp_cookie_here
```

**Step 2: Extend setup_auth.py**

Add a new step to `src/intervals_icu_mcp/scripts/setup_auth.py` after the existing Intervals.icu steps. Add this import at the top:

```python
from ..auth import update_env_key, update_tp_env_key
```

And add before the success message at the end of `main()`:

```python
    # Step 3: TrainingPeaks (optional)
    print()
    print("Step 3: TrainingPeaks Authentication (optional)")
    print("-" * 60)
    print("If you use TrainingPeaks for coaching, you can add your session cookie.")
    print("Skip this step if you don't use TrainingPeaks.")
    print()
    print("To find your cookie:")
    print("1. Log in to trainingpeaks.com in your browser")
    print("2. Open DevTools (F12 or right-click → Inspect)")
    print("3. Go to Application → Cookies → trainingpeaks.com")
    print("4. Find the cookie named: Production_tpAuth")
    print("5. Copy the full value")
    print()

    tp_cookie = input("Paste your Production_tpAuth cookie value (or press Enter to skip): ").strip()

    if tp_cookie:
        try:
            update_tp_env_key(tp_cookie)
            print("\n✅ TrainingPeaks cookie saved.")
        except Exception as e:
            print(f"\n⚠️  Could not save TrainingPeaks cookie: {str(e)}")
    else:
        print("\nSkipping TrainingPeaks setup.")
```

**Step 3: Verify setup script runs without error**

```bash
echo "" | uv run intervals-icu-mcp-auth
```

Expected: prompts appear, no crash (will fail on empty input, that's fine).

**Step 4: Commit**

```bash
git add .env.example src/intervals_icu_mcp/scripts/setup_auth.py
git commit -m "feat: add TrainingPeaks cookie to .env.example and setup script"
```

---

### Task 7: Run full test suite and lint

**Step 1: Run all tests**

```bash
uv run pytest -v
```

Expected: all PASS.

**Step 2: Run lint**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

Fix any issues with `uv run ruff format src/ tests/` then re-check.

**Step 3: Run type checking**

```bash
uv run pyright
```

Fix any type errors in the new files.

**Step 4: Final commit if any fixes were needed**

```bash
git add -p
git commit -m "fix: lint and type errors in TrainingPeaks integration"
```

---

### Task 8: Manual smoke test with real credentials

**Step 1: Run auth setup**

```bash
uv run intervals-icu-mcp-auth
```

Enter your Intervals credentials, then paste your `Production_tpAuth` cookie when prompted.

**Step 2: Verify .env has TP_AUTH_COOKIE set**

```bash
grep TP_AUTH_COOKIE .env
```

Expected: line with your cookie value.

**Step 3: Test auth check tool manually**

```bash
uv run python -c "
import asyncio
from intervals_icu_mcp.auth import load_tp_config
from intervals_icu_mcp.client import TPClient

async def test():
    config = load_tp_config()
    async with TPClient(config) as client:
        r = await client._request('GET', '/v1/athlete/self')
        print(r.status_code, r.json())

asyncio.run(test())
"
```

Expected: 200 and your TP athlete profile. If 401, your cookie is wrong or expired.

**Step 4: Start the server and verify tools appear**

```bash
uv run intervals-icu-mcp
```

In Claude Desktop, check that `tp_check_auth`, `tp_get_planned_workouts`, etc. appear in the tool list.
