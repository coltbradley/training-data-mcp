"""Additional performance curve tools for Intervals.icu MCP server."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastmcp import Context

from ..auth import ICUConfig
from ..client import ICUAPIError, ICUClient
from ..response_builder import ResponseBuilder


async def get_hr_curves(
    days_back: Annotated[int | None, "Number of days to analyze (optional)"] = None,
    time_period: Annotated[
        str | None,
        "Time period shorthand: 'week', 'month', 'year', 'all' (optional)",
    ] = None,
    ctx: Context | None = None,
) -> str:
    """Get heart rate curve data showing best efforts for various durations.

    Analyzes heart rate data across activities to find peak heart rate outputs for
    different time durations (e.g., 5 seconds, 1 minute, 5 minutes, 20 minutes).

    Useful for tracking cardiovascular fitness improvements and identifying HR zones
    across different effort durations.

    Args:
        days_back: Number of days to analyze (overrides time_period)
        time_period: Time period shorthand - 'week' (7 days), 'month' (30 days),
                     'year' (365 days), 'all' (all time). Default is 90 days.

    Returns:
        JSON string with HR curve data
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        # Determine date range
        oldest = None

        if days_back is not None:
            oldest_date = datetime.now() - timedelta(days=days_back)
            oldest = oldest_date.strftime("%Y-%m-%d")
            period_label = f"{days_back}_days"
        elif time_period:
            period_map = {
                "week": 7,
                "month": 30,
                "year": 365,
            }
            if time_period.lower() in period_map:
                days = period_map[time_period.lower()]
                oldest_date = datetime.now() - timedelta(days=days)
                oldest = oldest_date.strftime("%Y-%m-%d")
                period_label = time_period.lower()
            elif time_period.lower() == "all":
                oldest = None
                period_label = "all_time"
            else:
                return ResponseBuilder.build_error_response(
                    "Invalid time_period. Use 'week', 'month', 'year', or 'all'",
                    error_type="validation_error",
                )
        else:
            # Default to 90 days
            oldest_date = datetime.now() - timedelta(days=90)
            oldest = oldest_date.strftime("%Y-%m-%d")
            period_label = "90_days"

        async with ICUClient(config) as client:
            hr_curve = await client.get_hr_curves(oldest=oldest)

            if not hr_curve.data or len(hr_curve.data) == 0:
                return ResponseBuilder.build_response(
                    data={"hr_curve": [], "period": period_label},
                    metadata={
                        "message": f"No HR curve data available for {period_label}. "
                        "Complete some activities with heart rate to build your HR curve."
                    },
                )

            # Key durations to highlight (in seconds)
            key_durations = {
                5: "5_sec",
                15: "15_sec",
                30: "30_sec",
                60: "1_min",
                120: "2_min",
                300: "5_min",
                600: "10_min",
                1200: "20_min",
                3600: "1_hour",
            }

            # Find data points for key durations
            peak_efforts: dict[str, dict[str, Any]] = {}
            for seconds, label in key_durations.items():
                # Find closest data point
                closest_point = min(
                    hr_curve.data,
                    key=lambda p: abs(p.secs - seconds),
                    default=None,
                )

                if closest_point and abs(closest_point.secs - seconds) <= seconds * 0.1:
                    # Only include if within 10% of target duration
                    effort: dict[str, Any] = {
                        "bpm": closest_point.bpm,
                        "duration_seconds": closest_point.secs,
                    }
                    if closest_point.date:
                        effort["date"] = closest_point.date
                    if closest_point.src_activity_id:
                        effort["activity_id"] = closest_point.src_activity_id

                    peak_efforts[label] = effort

            # Calculate summary statistics
            max_hr_point = max(hr_curve.data, key=lambda p: p.bpm or 0)
            min_duration = min(hr_curve.data, key=lambda p: p.secs)
            max_duration = max(hr_curve.data, key=lambda p: p.secs)

            summary: dict[str, Any] = {
                "total_data_points": len(hr_curve.data),
                "max_hr_bpm": max_hr_point.bpm,
                "max_hr_duration_seconds": max_hr_point.secs,
                "duration_range": {
                    "min_seconds": min_duration.secs,
                    "max_seconds": max_duration.secs,
                },
            }

            # If we have dates, show range
            dates = [p.date for p in hr_curve.data if p.date]
            if dates:
                summary["effort_date_range"] = {"oldest": min(dates), "newest": max(dates)}

            # Calculate HR zones (based on max HR if available)
            hr_zones: dict[str, dict[str, int]] | None = None
            if max_hr_point.bpm:
                max_hr = max_hr_point.bpm
                zones = {
                    "zone_1_recovery": (0.50, 0.60),
                    "zone_2_endurance": (0.60, 0.70),
                    "zone_3_tempo": (0.70, 0.80),
                    "zone_4_threshold": (0.80, 0.90),
                    "zone_5_vo2max": (0.90, 1.00),
                }

                hr_zones = {}
                for zone_name, (low, high) in zones.items():
                    hr_zones[zone_name] = {
                        "min_bpm": int(max_hr * low),
                        "max_bpm": int(max_hr * high),
                        "min_percent_max": int(low * 100),
                        "max_percent_max": int(high * 100),
                    }

            result_data: dict[str, Any] = {
                "period": period_label,
                "peak_efforts": peak_efforts,
                "summary": summary,
            }

            if hr_zones:
                result_data["hr_zones"] = hr_zones

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="hr_curves",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )


async def get_pace_curves(
    days_back: Annotated[int | None, "Number of days to analyze (optional)"] = None,
    time_period: Annotated[
        str | None,
        "Time period shorthand: 'week', 'month', 'year', 'all' (optional)",
    ] = None,
    use_gap: Annotated[bool, "Use Grade Adjusted Pace (GAP) for running"] = False,
    ctx: Context | None = None,
) -> str:
    """Get pace curve data showing best efforts for various durations.

    Analyzes pace data across running/swimming activities to find best pace outputs for
    different time durations (e.g., 400m, 1km, 5km, 10km).

    Useful for tracking running fitness and race predictions. Can use Grade Adjusted Pace
    (GAP) to normalize for hills.

    Args:
        days_back: Number of days to analyze (overrides time_period)
        time_period: Time period shorthand - 'week' (7 days), 'month' (30 days),
                     'year' (365 days), 'all' (all time). Default is 90 days.
        use_gap: Use Grade Adjusted Pace (GAP) for running to account for hills

    Returns:
        JSON string with pace curve data
    """
    assert ctx is not None
    config: ICUConfig = ctx.get_state("config")

    try:
        # Determine date range
        oldest = None

        if days_back is not None:
            oldest_date = datetime.now() - timedelta(days=days_back)
            oldest = oldest_date.strftime("%Y-%m-%d")
            period_label = f"{days_back}_days"
        elif time_period:
            period_map = {
                "week": 7,
                "month": 30,
                "year": 365,
            }
            if time_period.lower() in period_map:
                days = period_map[time_period.lower()]
                oldest_date = datetime.now() - timedelta(days=days)
                oldest = oldest_date.strftime("%Y-%m-%d")
                period_label = time_period.lower()
            elif time_period.lower() == "all":
                oldest = None
                period_label = "all_time"
            else:
                return ResponseBuilder.build_error_response(
                    "Invalid time_period. Use 'week', 'month', 'year', or 'all'",
                    error_type="validation_error",
                )
        else:
            # Default to 90 days
            oldest_date = datetime.now() - timedelta(days=90)
            oldest = oldest_date.strftime("%Y-%m-%d")
            period_label = "90_days"

        async with ICUClient(config) as client:
            pace_curve = await client.get_pace_curves(oldest=oldest, use_gap=use_gap)

            if not pace_curve.data or len(pace_curve.data) == 0:
                return ResponseBuilder.build_response(
                    data={"pace_curve": [], "period": period_label, "gap_enabled": use_gap},
                    metadata={
                        "message": f"No pace curve data available for {period_label}. "
                        "Complete some runs/swims to build your pace curve."
                    },
                )

            # Key distances to highlight (in meters)
            key_distances = {
                400: "400m",
                800: "800m",
                1000: "1km",
                1609.34: "1_mile",
                5000: "5km",
                10000: "10km",
                21097: "half_marathon",
            }

            def _format_pace_per_mi(pace_min_km: float) -> str:
                """Convert min/km to formatted min:sec /mi string."""
                pace_per_mi = pace_min_km * 1.60934
                mins = int(pace_per_mi)
                secs = int((pace_per_mi - mins) * 60)
                return f"{mins}:{secs:02d} /mi"

            # Find data points for key distances
            points_with_dist = [p for p in pace_curve.data if p.distance_meters]
            peak_efforts: dict[str, dict[str, Any]] = {}
            for target_m, label in key_distances.items():
                if not points_with_dist:
                    break
                closest_point = min(
                    points_with_dist,
                    key=lambda p: abs((p.distance_meters or 0) - target_m),
                    default=None,
                )

                if (
                    closest_point
                    and abs((closest_point.distance_meters or 0) - target_m) <= target_m * 0.05
                ):
                    effort: dict[str, Any] = {
                        "distance_meters": closest_point.distance_meters,
                        "time_seconds": closest_point.secs,
                        "pace_min_per_km": closest_point.pace,
                    }
                    if closest_point.pace:
                        effort["pace_per_mi"] = _format_pace_per_mi(closest_point.pace)
                    if closest_point.src_activity_id:
                        effort["activity_id"] = closest_point.src_activity_id
                        # Look up activity name/date from activities dict
                        act_info = pace_curve.activities.get(closest_point.src_activity_id)
                        if act_info:
                            effort["activity_name"] = act_info.get("name")
                            effort["date"] = act_info.get("start_date_local", "")[:10]

                    peak_efforts[label] = effort

            # Summary statistics
            best_pace_point = min(points_with_dist, key=lambda p: p.pace or float("inf"))
            shortest = min(points_with_dist, key=lambda p: p.distance_meters or 0)
            longest = max(points_with_dist, key=lambda p: p.distance_meters or 0)

            summary: dict[str, Any] = {
                "total_data_points": len(pace_curve.data),
                "fastest_pace_min_per_km": best_pace_point.pace,
                "fastest_pace_per_mi": _format_pace_per_mi(best_pace_point.pace)
                if best_pace_point.pace
                else None,
                "fastest_pace_distance_meters": best_pace_point.distance_meters,
                "distance_range_meters": {
                    "min": shortest.distance_meters,
                    "max": longest.distance_meters,
                },
                "gap_enabled": use_gap,
            }

            # Include pace models (critical speed, etc.) if available
            if pace_curve.pace_models:
                for model in pace_curve.pace_models:
                    if model.get("type") == "CS":
                        cs = model.get("criticalSpeed", 0)
                        if cs > 0:
                            cs_min_km = (1000 / cs) / 60
                            summary["critical_speed_m_per_s"] = round(cs, 3)
                            summary["critical_speed_per_mi"] = _format_pace_per_mi(cs_min_km)

            # Include curve set date range
            if pace_curve.curve_set:
                summary["curve_period"] = {
                    "label": pace_curve.curve_set.label,
                    "start": pace_curve.curve_set.start_date_local,
                    "end": pace_curve.curve_set.end_date_local,
                }

            result_data: dict[str, Any] = {
                "period": period_label,
                "peak_efforts": peak_efforts,
                "summary": summary,
            }

            return ResponseBuilder.build_response(
                data=result_data,
                query_type="pace_curves",
            )

    except ICUAPIError as e:
        return ResponseBuilder.build_error_response(e.message, error_type="api_error")
    except Exception as e:
        return ResponseBuilder.build_error_response(
            f"Unexpected error: {str(e)}", error_type="internal_error"
        )
