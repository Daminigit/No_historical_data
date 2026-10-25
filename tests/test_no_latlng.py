"""tests/test_no_latlng.py — Test abort behaviour on ambiguous addresses."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def _write_project(tmp_path: Path, payload: dict) -> Path:
    p = tmp_path / "project.json"
    p.write_text(json.dumps(payload))
    return p


_CFG = {
    "search_radius_km": 15,
    "down_payment_pct": 20,
    "interest_rate_pct": 8.5,
    "tenure_years": 20,
}

_AVAILABLE_UNIT = {"type": "2BHK", "status": "available", "price_min_inr": 9_600_000}


def test_missing_latlng_and_no_api_key_exits(tmp_path):
    """No lat/lng + no API key → sys.exit with clear message."""
    project = {
        "project": {"name": "Test"},
        "location": {"address": "Whitefield", "city": "Bengaluru"},
        "units": [_AVAILABLE_UNIT],
    }
    path = _write_project(tmp_path, project)

    with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": ""}, clear=False):
        from steps.read_project import read_project
        with pytest.raises(SystemExit) as exc:
            read_project(str(path), _CFG)
        assert exc.value.code is not None
        assert "GOOGLE_MAPS_API_KEY" in str(exc.value.code)


def test_city_level_address_exits_clearly(tmp_path):
    """Address that resolves to a city bounding box → sys.exit with clear message."""
    project = {
        "project": {"name": "Test"},
        "location": {"address": "Bengaluru", "city": "Bengaluru"},
        "units": [_AVAILABLE_UNIT],
    }
    path = _write_project(tmp_path, project)

    # Fake geocode result: APPROXIMATE + large bounding box
    fake_result = {
        "geometry": {
            "location_type": "APPROXIMATE",
            "location": {"lat": 12.97, "lng": 77.59},
            "viewport": {
                "northeast": {"lat": 13.14, "lng": 77.78},
                "southwest": {"lat": 12.83, "lng": 77.46},
            },
        }
    }

    with patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "fake_key"}, clear=False):
        with patch("steps.read_project.geocode_address", return_value=fake_result):
            from steps.read_project import read_project
            with pytest.raises(SystemExit) as exc:
                read_project(str(path), _CFG)
            msg = str(exc.value.code)
            assert "city" in msg.lower() or "region" in msg.lower() or "precise" in msg.lower()


def test_missing_name_exits(tmp_path):
    """Project JSON without project.name → sys.exit."""
    project = {
        "location": {"lat": 12.98, "lng": 77.72, "city": "Bengaluru"},
        "units": [_AVAILABLE_UNIT],
    }
    path = _write_project(tmp_path, project)
    from steps.read_project import read_project
    with pytest.raises(SystemExit):
        read_project(str(path), _CFG)


def test_no_available_units_exits(tmp_path):
    """Project JSON with no available units → sys.exit."""
    project = {
        "project": {"name": "Test"},
        "location": {"lat": 12.98, "lng": 77.72, "city": "Bengaluru"},
        "units": [{"type": "2BHK", "status": "sold", "price_min_inr": 9_600_000}],
    }
    path = _write_project(tmp_path, project)
    from steps.read_project import read_project
    with pytest.raises(SystemExit):
        read_project(str(path), _CFG)


def test_custom_format_json_succeeds(tmp_path):
    """Alternate JSON format (flat name, latitude/longitude, configurations) parses successfully."""
    custom_project = {
        "project_name": "Skyline Heights",
        "latitude": 19.0760,
        "longitude": 72.8777,
        "city": "Mumbai",
        "address": "Bandra Kurla Complex",
        "configurations": [
            {
                "configuration": "2BHK",
                "price": 18000000,
            },
            {
                "configuration": "3BHK",
                "price_inr": 25000000,
            }
        ]
    }
    path = _write_project(tmp_path, custom_project)
    from steps.read_project import read_project
    data = read_project(str(path), _CFG)
    assert data.name == "Skyline Heights"
    assert data.lat == 19.0760
    assert data.lng == 72.8777
    assert data.city == "Mumbai"
    assert len(data.unit_emis) == 2
