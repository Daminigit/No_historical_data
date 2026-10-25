"""tests/test_geocode.py — Unit tests for coordinate validation logic."""
import pytest
from unittest.mock import patch, MagicMock
from steps.read_project import _is_precise


# Helper to build a fake geocode result
def _make_result(location_type: str, ne: dict, sw: dict, lat: float, lng: float) -> dict:
    return {
        "geometry": {
            "location_type": location_type,
            "location": {"lat": lat, "lng": lng},
            "viewport": {"northeast": ne, "southwest": sw},
        }
    }


# Small bounding box (< 5 km diagonal) — a neighbourhood
_SMALL_NE = {"lat": 12.985, "lng": 77.725}
_SMALL_SW = {"lat": 12.975, "lng": 77.715}

# Large bounding box (> 5 km diagonal) — a whole city
_LARGE_NE = {"lat": 13.10, "lng": 77.80}
_LARGE_SW = {"lat": 12.80, "lng": 77.50}

_PROJECT_LAT = 12.98
_PROJECT_LNG = 77.72
_RADIUS = 15


def test_valid_precise_point_is_kept():
    result = _make_result("ROOFTOP", _SMALL_NE, _SMALL_SW, 12.980, 77.720)
    ok, reason = _is_precise(result, _PROJECT_LAT, _PROJECT_LNG, _RADIUS)
    assert ok is True
    assert reason == ""


def test_approximate_location_type_is_dropped():
    result = _make_result("APPROXIMATE", _SMALL_NE, _SMALL_SW, 12.980, 77.720)
    ok, reason = _is_precise(result, _PROJECT_LAT, _PROJECT_LNG, _RADIUS)
    assert ok is False
    assert "APPROXIMATE" in reason


def test_large_bounding_box_is_dropped():
    result = _make_result("GEOMETRIC_CENTER", _LARGE_NE, _LARGE_SW, 12.98, 77.72)
    ok, reason = _is_precise(result, _PROJECT_LAT, _PROJECT_LNG, _RADIUS)
    assert ok is False
    assert "bounding box" in reason


def test_point_outside_radius_is_dropped():
    # Place 20 km away (beyond 15 km radius)
    result = _make_result("ROOFTOP", _SMALL_NE, _SMALL_SW, 13.16, 77.72)
    ok, reason = _is_precise(result, _PROJECT_LAT, _PROJECT_LNG, _RADIUS)
    assert ok is False
    assert "km from project" in reason


def test_point_at_edge_of_radius_is_kept():
    # ~14.6 km away (within 15 km radius)
    result = _make_result("ROOFTOP", _SMALL_NE, _SMALL_SW, 12.850, 77.720)
    ok, reason = _is_precise(result, _PROJECT_LAT, _PROJECT_LNG, _RADIUS)
    assert ok is True


def test_no_project_coords_skips_radius_check():
    """Without project coordinates, the radius check should be skipped."""
    result = _make_result("ROOFTOP", _SMALL_NE, _SMALL_SW, 12.980, 77.720)
    ok, reason = _is_precise(result, None, None, _RADIUS)
    assert ok is True
