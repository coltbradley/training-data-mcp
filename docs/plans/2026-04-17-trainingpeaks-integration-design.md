# TrainingPeaks integration design

**Date:** 2026-04-17
**Status:** Approved

## Problem

The intervals-icu-mcp server covers executed training data (actual activities, fitness metrics, performance curves). It has no visibility into the coaching side: what workouts are planned, what targets were set, and whether you hit them. TrainingPeaks is where the coach works, so that data lives there.

## Goal

Add a curated set of TrainingPeaks tools to the existing MCP server so Claude can answer coaching-side questions (planned workouts, targets, compliance) alongside execution-side questions (actual performance, fitness load) in the same conversation.

## Approach

Full port: adapt TrainingPeaks tools into the existing FastMCP + middleware + ResponseBuilder pattern. Not a separate server — one process, one config entry in Claude Desktop.

Reference implementation: https://github.com/JamsusMaximus/trainingpeaks-mcp

## Design

### Auth & config

- Add `TP_AUTH_COOKIE` to `.env` and `.env.example`
- Add `TPConfig` pydantic model to `auth.py` (mirrors `ICUConfig`)
- Extend `ConfigMiddleware` in `middleware.py` to load both configs and inject as separate context state keys:
  - `ctx.set_state("config", icu_config)` (unchanged)
  - `ctx.set_state("tp_config", tp_config)`
- If TP credentials are missing, TP tools return a structured error — the server does not crash

### HTTP client

- Add `TPClient` to `client.py` alongside `ICUClient`
- Target: `https://tpapi.trainingpeaks.com`
- Auth: cookie header (`Production_tpAuth`)
- Same async context manager pattern as `ICUClient`
- Raises `TPAPIError` for 401, 403, 404, 429
- 401/403 error message explicitly tells the user to re-extract the cookie from their browser

### Tools

Six tools in a new `tools/trainingpeaks.py` file. All follow the existing async pattern: `ctx` injection, `ResponseBuilder`, JSON string output.

| Tool                      | Purpose                                                          |
| ------------------------- | ---------------------------------------------------------------- |
| `tp_check_auth`           | Validate the cookie is still active                              |
| `tp_get_calendar`         | Full calendar view (planned + completed events) for a date range |
| `tp_get_planned_workouts` | Workouts the coach has scheduled                                 |
| `tp_get_workout_details`  | Targets for a specific workout (power, HR, duration, zones)      |
| `tp_get_compliance`       | How well completed workouts matched targets                      |
| `tp_get_athlete_metrics`  | TP's fitness/form numbers (ATL, CTL, TSB equivalent)             |

### Auth setup UX

- Extend `scripts/setup_auth.py` to prompt for the TP auth cookie after Intervals credentials
- Include instructions: DevTools → Application → Cookies → `Production_tpAuth`
- Cookie written to `.env` alongside existing credentials
- One setup flow, one file

## What this is not

- Not replacing any Intervals tools
- Not adding TP gear, equipment, workout library management, or settings tools
- Not cross-platform logic in the tools themselves — Claude handles synthesis in context

## Key risk

Cookie auth will expire. The mitigation is a clear error message on 401/403 and a simple re-run of the setup script to update `.env`.
