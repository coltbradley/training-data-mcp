"""TrainingPeaks tools for intervals-icu-mcp server.

Endpoint reference (verified against live TP API):
- GET /users/v3/user                                            -> user profile (userId, username)
- GET /fitness/v6/athletes/{id}/workouts/{start}/{end}          -> workouts in date range
- GET /fitness/v6/athletes/{id}/workouts/{workoutId}            -> single workout details
- POST /fitness/v1/athletes/{id}/reporting/performancedata/{s}/{e}  -> PMC (CTL/ATL/TSB) data

TP uses the same number for userId and athleteId for self-owned accounts, so
we derive athleteId from the user profile on each call.
"""

from datetime import date, timedelta
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
        "Go to Application \u2192 Cookies \u2192 trainingpeaks.com",
        "Copy the value of Production_tpAuth",
        "Re-run intervals-icu-mcp-auth and paste it when prompted",
    ],
)


async def _get_user_info(client: TPClient) -> tuple[int, str | None]:
    """Fetch TP user profile. Returns (athlete_id, username)."""
    resp = await client.request("GET", "/users/v3/user")
    payload = resp.json()
    user = payload.get("user") if isinstance(payload, dict) else None
    if not isinstance(user, dict):
        raise TPAPIError("Unexpected /users/v3/user response shape", resp.status_code)
    user_id = user.get("userId")
    if not isinstance(user_id, int):
        raise TPAPIError("No userId in TrainingPeaks profile response", resp.status_code)
    username = user.get("userName") or user.get("username")
    return user_id, username


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
            athlete_id, username = await _get_user_info(client)
            return ResponseBuilder.build_response(
                data={
                    "authenticated": True,
                    "athlete_id": athlete_id,
                    "username": username,
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
            athlete_id, _ = await _get_user_info(client)
            resp = await client.request(
                "GET",
                f"/fitness/v6/athletes/{athlete_id}/workouts/{start_date}/{end_date}",
            )
            workouts = resp.json()

            planned: list[dict[str, Any]] = []
            for w in workouts:
                planned.append(
                    {
                        "workout_id": w.get("workoutId"),
                        "date": (w.get("workoutDay") or "").split("T")[0] or None,
                        "title": w.get("title"),
                        "workout_type_id": w.get("workoutTypeValueId"),
                        "description": w.get("description"),
                        "coach_comments": w.get("coachComments"),
                        "planned_duration_secs": w.get("totalTimePlanned"),
                        "planned_distance_meters": w.get("distancePlanned"),
                        "planned_tss": w.get("tssPlanned"),
                        "planned_if": w.get("ifPlanned"),
                        "completed": bool(w.get("completed")),
                    }
                )

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
            athlete_id, _ = await _get_user_info(client)
            resp = await client.request(
                "GET",
                f"/fitness/v6/athletes/{athlete_id}/workouts/{workout_id}",
            )
            w = resp.json()

            return ResponseBuilder.build_response(
                data={
                    "workout_id": w.get("workoutId"),
                    "title": w.get("title"),
                    "date": (w.get("workoutDay") or "").split("T")[0] or None,
                    "workout_type_id": w.get("workoutTypeValueId"),
                    "description": w.get("description"),
                    "coach_comments": w.get("coachComments"),
                    "planned_duration_secs": w.get("totalTimePlanned"),
                    "planned_distance_meters": w.get("distancePlanned"),
                    "planned_tss": w.get("tssPlanned"),
                    "planned_if": w.get("ifPlanned"),
                    "actual_duration_secs": w.get("totalTime"),
                    "actual_distance_meters": w.get("distance"),
                    "actual_tss": w.get("tssActual"),
                    "structure": w.get("structure"),
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
            athlete_id, _ = await _get_user_info(client)
            resp = await client.request(
                "GET",
                f"/fitness/v6/athletes/{athlete_id}/workouts/{start_date}/{end_date}",
            )
            workouts = resp.json()

            compliance_data: list[dict[str, Any]] = []
            for w in workouts:
                has_planned = w.get("totalTimePlanned") or w.get("tssPlanned")
                has_actual = w.get("totalTime") or w.get("tssActual")
                if has_planned and has_actual:
                    compliance_data.append(
                        {
                            "workout_id": w.get("workoutId"),
                            "date": (w.get("workoutDay") or "").split("T")[0] or None,
                            "title": w.get("title"),
                            "planned_duration_secs": w.get("totalTimePlanned"),
                            "actual_duration_secs": w.get("totalTime"),
                            "planned_tss": w.get("tssPlanned"),
                            "actual_tss": w.get("tssActual"),
                            "planned_distance_meters": w.get("distancePlanned"),
                            "actual_distance_meters": w.get("distance"),
                            "compliance_code": w.get("complianceDurationPercent"),
                        }
                    )

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
            athlete_id, _ = await _get_user_info(client)
            resp = await client.request(
                "GET",
                f"/fitness/v6/athletes/{athlete_id}/workouts/{start_date}/{end_date}",
            )
            items = resp.json()

            by_date: dict[str, list[dict[str, Any]]] = {}
            for item in items:
                date_key = (item.get("workoutDay") or "unknown").split("T")[0]
                by_date.setdefault(date_key, []).append(
                    {
                        "id": item.get("workoutId"),
                        "title": item.get("title"),
                        "workout_type_id": item.get("workoutTypeValueId"),
                        "planned_duration_secs": item.get("totalTimePlanned"),
                        "completed": bool(item.get("completed")),
                        "tss_planned": item.get("tssPlanned"),
                        "tss_actual": item.get("tssActual"),
                    }
                )

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
    """Get TrainingPeaks fitness metrics (CTL/ATL/TSB).

    Returns TrainingPeaks' own training load numbers for the most recent 90 days.
    Compare with Intervals.icu's get_fitness_summary to see if the platforms agree.

    Returns:
        JSON with TP fitness metrics (current CTL/ATL/TSB plus daily history)
    """
    assert ctx is not None
    config = _require_tp_config(ctx)
    if not config:
        return _TP_NOT_CONFIGURED

    try:
        async with TPClient(config) as client:
            athlete_id, _ = await _get_user_info(client)

            end = date.today()
            start = end - timedelta(days=90)
            body = {
                "atlConstant": 7,
                "atlStart": 0,
                "ctlConstant": 42,
                "ctlStart": 0,
                "workoutTypes": [],
            }
            resp = await client.request(
                "POST",
                f"/fitness/v1/athletes/{athlete_id}/reporting/performancedata/{start}/{end}",
                json=body,
            )
            entries = resp.json() or []

            daily: list[dict[str, Any]] = []
            for entry in entries:
                day = (entry.get("workoutDay") or "").split("T")[0]
                daily.append(
                    {
                        "date": day,
                        "tss": entry.get("tssActual"),
                        "ctl": round(entry.get("ctl") or 0, 1),
                        "atl": round(entry.get("atl") or 0, 1),
                        "tsb": round(entry.get("tsb") or 0, 1),
                    }
                )

            current = daily[-1] if daily else None
            return ResponseBuilder.build_response(
                data={
                    "current": current,
                    "history": daily,
                },
                metadata={"start_date": str(start), "end_date": str(end)},
                query_type="tp_athlete_metrics",
            )
    except TPAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
