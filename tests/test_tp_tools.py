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
        tp_respx_mock.get("/v1/athlete/self").mock(
            return_value=Response(200, json={"userId": 42, "username": "colt"})
        )
        result = await tp_check_auth(ctx=mock_tp_ctx)
        response = json.loads(result)
        assert "data" in response
        assert response["data"]["authenticated"] is True
        assert response["data"]["user_id"] == 42
        assert response["data"]["username"] == "colt"

    async def test_returns_error_when_cookie_invalid(self, mock_tp_ctx, tp_respx_mock):
        tp_respx_mock.get("/v1/athlete/self").mock(return_value=Response(401))
        result = await tp_check_auth(ctx=mock_tp_ctx)
        response = json.loads(result)
        assert "error" in response

    async def test_returns_error_when_creds_missing(self):
        ctx = MagicMock()
        ctx.get_state.side_effect = lambda k: TPConfig(tp_auth_cookie="") if k == "tp_config" else None
        result = await tp_check_auth(ctx=ctx)
        response = json.loads(result)
        assert "error" in response
        assert response["error"]["type"] == "auth_error"


class TestTPGetPlannedWorkouts:
    async def test_returns_planned_workouts(self, mock_tp_ctx, tp_respx_mock):
        tp_respx_mock.get("/v1/athlete/self").mock(
            return_value=Response(200, json={"userId": 42})
        )
        tp_respx_mock.get("/v1/workouts/2026-04-14/2026-04-20").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "workoutId": 1,
                        "workoutDay": "2026-04-15",
                        "title": "Zone 2 Run",
                        "workoutTypeValueId": 3,
                        "totalTimePlanned": 3600,
                        "totalDistancePlanned": 10000,
                        "tssPlanned": 50,
                        "description": "Easy aerobic run",
                    }
                ],
            )
        )
        result = await tp_get_planned_workouts(
            start_date="2026-04-14", end_date="2026-04-20", ctx=mock_tp_ctx
        )
        response = json.loads(result)
        assert "data" in response
        assert len(response["data"]["workouts"]) == 1
        assert response["data"]["workouts"][0]["title"] == "Zone 2 Run"
        assert response["data"]["workouts"][0]["planned_duration_secs"] == 3600
        assert response["data"]["count"] == 1

    async def test_missing_tp_credentials_returns_error(self):
        ctx = MagicMock()
        ctx.get_state.side_effect = (
            lambda k: TPConfig(tp_auth_cookie="") if k == "tp_config" else None
        )
        result = await tp_get_planned_workouts(
            start_date="2026-04-14", end_date="2026-04-20", ctx=ctx
        )
        response = json.loads(result)
        assert "error" in response
        assert response["error"]["type"] == "auth_error"

    async def test_returns_empty_list_for_no_workouts(self, mock_tp_ctx, tp_respx_mock):
        tp_respx_mock.get("/v1/athlete/self").mock(
            return_value=Response(200, json={"userId": 42})
        )
        tp_respx_mock.get("/v1/workouts/2026-04-14/2026-04-20").mock(
            return_value=Response(200, json=[])
        )
        result = await tp_get_planned_workouts(
            start_date="2026-04-14", end_date="2026-04-20", ctx=mock_tp_ctx
        )
        response = json.loads(result)
        assert response["data"]["count"] == 0
        assert response["data"]["workouts"] == []


class TestTPGetWorkoutDetails:
    async def test_returns_workout_details(self, mock_tp_ctx, tp_respx_mock):
        tp_respx_mock.get("/v1/workouts/999").mock(
            return_value=Response(
                200,
                json={
                    "workoutId": 999,
                    "title": "Threshold Intervals",
                    "workoutDay": "2026-04-15",
                    "description": "5x5min at FTP",
                    "coachComments": "Focus on pacing",
                    "totalTimePlanned": 3600,
                    "totalDistancePlanned": 12000,
                    "tssPlanned": 80,
                    "structure": {"steps": []},
                },
            )
        )
        result = await tp_get_workout_details(workout_id="999", ctx=mock_tp_ctx)
        response = json.loads(result)
        assert "data" in response
        assert response["data"]["workout_id"] == 999
        assert response["data"]["title"] == "Threshold Intervals"
        assert response["data"]["coach_comments"] == "Focus on pacing"

    async def test_missing_creds_returns_error(self):
        ctx = MagicMock()
        ctx.get_state.side_effect = (
            lambda k: TPConfig(tp_auth_cookie="") if k == "tp_config" else None
        )
        result = await tp_get_workout_details(workout_id="999", ctx=ctx)
        response = json.loads(result)
        assert "error" in response


class TestTPGetCompliance:
    async def test_filters_to_workouts_with_both_planned_and_actual(
        self, mock_tp_ctx, tp_respx_mock
    ):
        tp_respx_mock.get("/v1/workouts/2026-04-14/2026-04-20").mock(
            return_value=Response(
                200,
                json=[
                    {
                        "workoutId": 1,
                        "workoutDay": "2026-04-15",
                        "title": "Zone 2 Run",
                        "totalTimePlanned": 3600,
                        "totalTime": 3500,
                        "tssPlanned": 50,
                        "tss": 48,
                        "complianceCode": "G",
                    },
                    {
                        "workoutId": 2,
                        "workoutDay": "2026-04-16",
                        "title": "Planned Only",
                        "totalTimePlanned": 1800,
                        "totalTime": None,  # not completed
                        "tssPlanned": 30,
                    },
                    {
                        "workoutId": 3,
                        "workoutDay": "2026-04-17",
                        "title": "No Plan",
                        "totalTimePlanned": None,
                        "totalTime": 2400,
                    },
                ],
            )
        )
        result = await tp_get_compliance(
            start_date="2026-04-14", end_date="2026-04-20", ctx=mock_tp_ctx
        )
        response = json.loads(result)
        assert "data" in response
        # Only workout 1 has both planned and actual
        assert response["data"]["count"] == 1
        assert response["data"]["compliance"][0]["workout_id"] == 1
        assert response["data"]["compliance"][0]["actual_duration_secs"] == 3500
        assert response["data"]["compliance"][0]["compliance_code"] == "G"

    async def test_missing_creds_returns_error(self):
        ctx = MagicMock()
        ctx.get_state.side_effect = (
            lambda k: TPConfig(tp_auth_cookie="") if k == "tp_config" else None
        )
        result = await tp_get_compliance(
            start_date="2026-04-14", end_date="2026-04-20", ctx=ctx
        )
        response = json.loads(result)
        assert "error" in response


class TestTPGetCalendar:
    async def test_groups_items_by_date(self, mock_tp_ctx, tp_respx_mock):
        tp_respx_mock.get("/v1/workouts/2026-04-14/2026-04-20").mock(
            return_value=Response(
                200,
                json=[
                    {"workoutId": 1, "workoutDay": "2026-04-15", "title": "Run", "tssPlanned": 50},
                    {"workoutId": 2, "workoutDay": "2026-04-15", "title": "Swim", "tssPlanned": 30},
                    {"workoutId": 3, "workoutDay": "2026-04-16", "title": "Bike", "tssPlanned": 70},
                ],
            )
        )
        result = await tp_get_calendar(
            start_date="2026-04-14", end_date="2026-04-20", ctx=mock_tp_ctx
        )
        response = json.loads(result)
        assert "data" in response
        assert response["data"]["total_items"] == 3
        assert len(response["data"]["calendar"]["2026-04-15"]) == 2
        assert len(response["data"]["calendar"]["2026-04-16"]) == 1

    async def test_missing_creds_returns_error(self):
        ctx = MagicMock()
        ctx.get_state.side_effect = (
            lambda k: TPConfig(tp_auth_cookie="") if k == "tp_config" else None
        )
        result = await tp_get_calendar(
            start_date="2026-04-14", end_date="2026-04-20", ctx=ctx
        )
        response = json.loads(result)
        assert "error" in response


class TestTPGetAthleteMetrics:
    async def test_returns_fitness_metrics(self, mock_tp_ctx, tp_respx_mock):
        tp_respx_mock.get("/v1/athlete/self").mock(
            return_value=Response(200, json={"userId": 42})
        )
        tp_respx_mock.get("/fitness/v6/athletes/42/fitness").mock(
            return_value=Response(
                200,
                json={"atl": 45.2, "ctl": 58.1, "tsb": 12.9, "rampRate": 2.1},
            )
        )
        result = await tp_get_athlete_metrics(ctx=mock_tp_ctx)
        response = json.loads(result)
        assert "data" in response
        assert response["data"]["atl"] == 45.2
        assert response["data"]["ctl"] == 58.1
        assert response["data"]["tsb"] == 12.9
        assert response["data"]["ramp_rate"] == 2.1

    async def test_missing_creds_returns_error(self):
        ctx = MagicMock()
        ctx.get_state.side_effect = (
            lambda k: TPConfig(tp_auth_cookie="") if k == "tp_config" else None
        )
        result = await tp_get_athlete_metrics(ctx=ctx)
        response = json.loads(result)
        assert "error" in response
