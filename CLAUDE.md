# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an MCP (Model Context Protocol) server for Intervals.icu that provides 48 tools, 1 resource, and 6 prompts for accessing training data, wellness metrics, and performance analysis through Claude and other LLMs.

Repo name is `intervals-icu-mcp`; the published Docker image is `ghcr.io/coltbradley/training-data-mcp`. The FastMCP server identifies itself as `"Training Data"`.

A TrainingPeaks integration was attempted and removed — TP's API enforces TLS fingerprinting plus single-use cookie rotation, which makes server-side automation unworkable without a headless browser or partner OAuth credentials.

Supports both stdio (local) and streamable-HTTP (remote, Docker) transports. Transport is controlled by `MCP_TRANSPORT` env var (`stdio` default; `http` used in Docker). HTTP mode exposes `/mcp` for the MCP protocol and `/health` for liveness checks.

## Development Commands

### Setup & Dependencies

```bash
# Install dependencies
make install

# Update dependencies
make update

# Setup authentication
make auth
```

### Testing & Linting

```bash
# Run all pre-release checks (same as CI)
make can-release

# Run tests
make test

# Run specific test filter
make test/athlete         # runs tests matching "athlete"

# Run tests with verbose output
make test/verbose

# Lint with ruff and pyright
make lint

# Format code
make format
```

### Running Locally

```bash
# Run the MCP server
make run
```

### Docker

```bash
# Build Docker image
make docker/build

# Run Docker container
make docker/run
```

## Architecture

### Core Components

**FastMCP Server** (`server.py`)

- Entry point that initializes the FastMCP server
- Registers all tools, resources, and prompts
- Tools are imported from `tools/` modules but registered in server.py
- Middleware is added before tools are registered

**Middleware** (`middleware.py`)

- `ConfigMiddleware` runs before every tool call
- Loads and validates Intervals.icu configuration from environment (raises `ToolError` if missing)
- Injects `ICUConfig` into context state as `"config"`
- Tools access config via `ctx.get_state("config")`

**API Client** (`client.py`)

- `ICUClient` — async httpx client for Intervals.icu. Basic Auth with username `"API_KEY"`. Raises `ICUAPIError`.
- Async context manager, 30s timeout default.

**Authentication** (`auth.py`)

- `ICUConfig` uses pydantic-settings to load from `.env`
- `load_config()` returns the config
- `validate_credentials()` checks presence (treats placeholder values as invalid)
- `update_env_key()` persists credentials to `.env`
- Interactive setup: `scripts/setup_auth.py` (runs via `make auth` or `intervals-icu-mcp-auth`)

**Response Builder** (`response_builder.py`)

- All tools return JSON with consistent structure:
  ```json
  {
    "data": {...},           // Main data payload
    "analysis": {...},       // Optional insights and computed metrics
    "metadata": {...}        // Query metadata, timestamps
  }
  ```
- `ResponseBuilder.build_response()` creates success responses
- `ResponseBuilder.build_error_response()` creates error responses
- Automatically converts datetime objects to ISO strings

**Models** (`models.py`)

- Pydantic models for all API responses
- Models include: Activity, Athlete, Wellness, Event, PowerCurve, etc.

### Tool Organization

Tools are organized into 11 modules in `tools/` (grouped into 9 user-facing categories — `events.py` + `event_management.py` together are "Events/Calendar", `performance.py` + `curves.py` together are "Performance/Curves"):

1. **activities.py** - Query and manage activities (10 tools)
2. **activity_analysis.py** - Streams, intervals, best efforts, histograms (8 tools)
3. **athlete.py** - Profile and fitness metrics (CTL/ATL/TSB) (2 tools)
4. **wellness.py** - HRV, sleep, recovery metrics (3 tools)
5. **events.py** - Calendar queries (3 tools)
6. **event_management.py** - Create/update/delete/bulk/duplicate events (6 tools)
7. **performance.py** - Power curves (1 tool)
8. **curves.py** - HR and pace curves (2 tools)
9. **workout_library.py** - Browse workout folders and plans (2 tools)
10. **gear.py** - Gear and maintenance reminders (6 tools)
11. **sport_settings.py** - FTP, FTHR, pace thresholds (5 tools)

### Tool Pattern

All tools follow the same async pattern:

```python
async def tool_name(
    param: str,
    ctx: Context | None = None,
) -> str:
    """Tool description."""
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        async with ICUClient(config) as client:
            # Make API calls
            result = await client.method()

            # Build response
            return ResponseBuilder.build_response(
                data={"key": "value"},
                analysis={"insights": "..."},
                query_type="tool_type"
            )
    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
```

## Important Implementation Details

### Authentication Flow

1. User runs `make setup` (or `make auth`) — prompts for Intervals API key and athlete ID
2. Credentials stored in `.env` (`INTERVALS_ICU_API_KEY`, `INTERVALS_ICU_ATHLETE_ID`)
3. `ConfigMiddleware` loads + validates credentials on every tool call
4. `ICUClient` uses HTTP Basic Auth with username `"API_KEY"`

### Error Handling

- `ICUAPIError` for API errors (401, 404, 429, etc.)
- Middleware raises `ToolError` if credentials not configured
- All tools return error JSON instead of raising exceptions
- Include helpful error messages and suggestions

### Response Format

- Never return raw API responses
- Always use `ResponseBuilder.build_response()` for consistency
- Include `analysis` section for insights when relevant
- Use `metadata` for query context (date ranges, limits, etc.)

### Date Handling

- API uses ISO-8601 format (YYYY-MM-DD or full datetime)
- `ResponseBuilder.format_date_with_day()` adds day-of-week info
- All datetimes automatically converted to ISO strings in responses

### Testing

- Tests use `pytest` with `pytest-asyncio` for async tests
- `respx` is used to mock HTTP requests
- Test fixtures in `tests/fixtures/`
- Test stubs in `tests/stubs/`

## Type Checking

- Pyright is configured with basic type checking mode
- Strict mode only for `src/` directory
- Allow imports without type stubs
- Run `make lint/pyright` or `uv run pyright`

## Code Style

- Ruff for linting and formatting
- Line length: 100 characters
- Target Python 3.11+
- Ignore E501 (line length enforced by formatter)
- Allow unused imports in `__init__.py` files
- Run `make format` to auto-fix style issues

## Important Files

- `.env` - Local credentials (not in git)
- `.env.example` - Template for credentials
- `openapi-spec.json` - Intervals.icu API specification
- `uv.lock` - Locked dependencies (commit this)
- `Dockerfile` - Multi-stage build, runs HTTP transport on port 8080
- `docker-compose.yml` - Local Docker run (builds locally)
- `docker-compose.truenas.yml` - TrueNAS SCALE deployment (uses published image + watchtower)
- `.github/workflows/test.yml` - CI tests
- `.github/workflows/release.yml` - Docker publish to `ghcr.io/coltbradley/training-data-mcp`
