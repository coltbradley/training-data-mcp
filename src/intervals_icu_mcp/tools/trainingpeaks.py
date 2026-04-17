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
        "Go to Application \u2192 Cookies \u2192 trainingpeaks.com",
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
            athlete_resp = await client._request("GET", "/v1/athlete/self")
            user_id = athlete_resp.json().get("userId")  # noqa: F841 — reserved for future use

            workouts_resp = await client._request("GET", f"/v1/workouts/{start_date}/{end_date}")
            workouts = workouts_resp.json()

            planned = []
            for w in workouts:
                workout: dict[str, Any] = {
                    "workout_id": w.get("workoutId"),
                    "date": w.get("workoutDay"),
                    "title": w.get("title"),
                    "sport": w.get("workoutTypeValueId"),
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
            response = await client._request("GET", f"/v1/workouts/{start_date}/{end_date}")
            workouts = response.json()

            compliance_data = []
            for w in workouts:
                if w.get("totalTimePlanned") and w.get("totalTime"):
                    compliance_data.append(
                        {
                            "workout_id": w.get("workoutId"),
                            "date": w.get("workoutDay"),
                            "title": w.get("title"),
                            "planned_duration_secs": w.get("totalTimePlanned"),
                            "actual_duration_secs": w.get("totalTime"),
                            "planned_tss": w.get("tssPlanned"),
                            "actual_tss": w.get("tss"),
                            "planned_distance_meters": w.get("totalDistancePlanned"),
                            "actual_distance_meters": w.get("totalDistance"),
                            "compliance_code": w.get("complianceCode"),
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
            response = await client._request("GET", f"/v1/workouts/{start_date}/{end_date}")
            items = response.json()

            by_date: dict[str, list[dict[str, Any]]] = {}
            for item in items:
                date = item.get("workoutDay", "unknown")
                if date not in by_date:
                    by_date[date] = []
                by_date[date].append(
                    {
                        "id": item.get("workoutId"),
                        "title": item.get("title"),
                        "sport": item.get("workoutTypeValueId"),
                        "planned_duration_secs": item.get("totalTimePlanned"),
                        "completed": item.get("completed", False),
                        "tss_planned": item.get("tssPlanned"),
                        "tss_actual": item.get("tss"),
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
            athlete_resp = await client._request("GET", "/v1/athlete/self")
            athlete = athlete_resp.json()
            user_id = athlete.get("userId")

            metrics_resp = await client._request(
                "GET", f"/fitness/v6/athletes/{user_id}/fitness"
            )
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
