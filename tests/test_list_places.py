"""
tests/test_list_places.py — Tests for Step 2 LLM place listing with Groq.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from models import ProjectData
from steps.list_places import _parse_response, _strip_coordinate_fields, list_places


def test_strip_coordinate_fields():
    data = {
        "name": "ITPL",
        "lat": 12.98,
        "lng": 77.72,
        "latitude": 12.98,
        "longitude": 77.72,
        "distance_km": 5.2,
        "drive_minutes": 15,
        "valid_field": "keep_me",
    }
    cleaned = _strip_coordinate_fields(data)
    assert "lat" not in cleaned
    assert "lng" not in cleaned
    assert "latitude" not in cleaned
    assert "longitude" not in cleaned
    assert "distance_km" not in cleaned
    assert "drive_minutes" not in cleaned
    assert cleaned["name"] == "ITPL"
    assert cleaned["valid_field"] == "keep_me"


def test_parse_response_success():
    payload = json.dumps({
        "it_parks": [{"name": "ITPL"}],
        "rental_areas": [
            {
                "name": "Hoodi",
                "rent_2bhk": 32000,
                "rent_3bhk": 45000,
                "source_url": "https://example.com/rents",
                "source_date": "2024-10-01",
            },
            {
                "name": "NoSourceArea",
                "rent_2bhk": 30000,
            }
        ]
    })
    it_parks, rentals = _parse_response(payload)
    assert len(it_parks) == 1
    assert it_parks[0]["name"] == "ITPL"
    assert len(rentals) == 1
    assert rentals[0]["name"] == "Hoodi"


def test_list_places_calls_groq(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "dummy_key")
    project = ProjectData(
        name="Test Project",
        address="Whitefield",
        city="Bengaluru",
        lat=12.98,
        lng=77.72,
    )
    cfg = {"search_radius_km": 15}

    mock_json_response = json.dumps({
        "it_parks": [{"name": "Bagmane Tech Park"}],
        "rental_areas": [
            {
                "name": "Indiranagar",
                "rent_2bhk": 40000,
                "rent_3bhk": 60000,
                "source_url": "https://example.com/indiranagar",
                "source_date": "2024-10-01",
            }
        ]
    })

    with patch("steps.list_places._call_llm", return_value=mock_json_response):
        places = list_places(project, cfg)

    assert len(places) == 2
    types = [p.place_type for p in places]
    assert "it_park" in types
    assert "rental_area" in types
    rental = next(p for p in places if p.place_type == "rental_area")
    assert rental.rent_2bhk == 40000.0
    assert rental.rent_source == "https://example.com/indiranagar"


def test_list_places_extracts_trending_keywords(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "dummy_key")
    project = ProjectData(
        name="Test Project",
        address="Whitefield",
        city="Bengaluru",
        lat=12.98,
        lng=77.72,
    )
    cfg = {"search_radius_km": 15}

    mock_json = json.dumps({
        "it_parks": [
            {
                "name": "ITPL",
                "trending_keywords": ["flats near ITPL", "apartments near ITPL"],
            }
        ],
        "rental_areas": [
            {
                "name": "Whitefield",
                "rent_2bhk": 35000,
                "source_url": "https://example.com/rents",
                "trending_keywords": ["flats in Whitefield", "luxury 3 BHK Whitefield"],
            }
        ]
    })

    with patch("steps.list_places._call_llm", return_value=mock_json):
        places = list_places(project, cfg)

    itpl = next(p for p in places if p.name == "ITPL")
    assert "flats near ITPL" in itpl.trending_keywords
    whitefield = next(p for p in places if p.name == "Whitefield")
    assert "flats in Whitefield" in whitefield.trending_keywords
