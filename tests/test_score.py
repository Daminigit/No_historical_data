"""tests/test_score.py — Unit tests for the scoring logic."""
import pytest
from models import Place, ProjectData, UnitEMI
from steps.score import score_places, _score_it_park, _band_for_ratio, _best_ratio

_CFG = {
    "max_drive_minutes": 45,
    "ratio_bands": [
        {"ratio_max": 0.30, "score": 1,  "label": "low"},
        {"ratio_max": 0.45, "score": 5,  "label": "medium"},
        {"ratio_max": 0.90, "score": 10, "label": "high"},
        {"ratio_max": 9999, "score": 5,  "label": "medium"},
    ],
}

_PROJECT = ProjectData(
    name="Test", lat=12.98, lng=77.72, city="Bengaluru", address="Whitefield",
    unit_emis=[
        UnitEMI(unit_type="2BHK", price_min_inr=9_600_000, emi_monthly=67_000),
        UnitEMI(unit_type="3BHK", price_min_inr=13_500_000, emi_monthly=94_200),
    ],
)


# --- IT park scoring ---

def test_it_park_short_drive_scores_high():
    score = _score_it_park(10, 45)
    assert score >= 7.5


def test_it_park_long_drive_scores_low():
    score = _score_it_park(40, 45)
    assert score < 4


def test_it_park_closer_beats_farther():
    assert _score_it_park(10, 45) > _score_it_park(40, 45)


def test_it_park_max_drive_scores_one():
    score = _score_it_park(45, 45)
    assert abs(score - 1.0) < 0.01


# --- Ratio band lookup ---

def test_ratio_053_is_high():
    band = _band_for_ratio(0.53, _CFG["ratio_bands"])
    assert band["label"] == "high"


def test_ratio_020_is_low():
    band = _band_for_ratio(0.20, _CFG["ratio_bands"])
    assert band["label"] == "low"


def test_ratio_110_is_medium():
    band = _band_for_ratio(1.10, _CFG["ratio_bands"])
    assert band["label"] == "medium"


def test_ratio_035_is_medium():
    band = _band_for_ratio(0.35, _CFG["ratio_bands"])
    assert band["label"] == "medium"


# --- Best ratio selection ---

def test_best_ratio_picks_highest():
    place = Place(name="Test Area", place_type="rental_area",
                  rent_2bhk=35_000, rent_3bhk=50_000)
    ratio, emi, label = _best_ratio(place, _PROJECT.unit_emis)
    # 2BHK: 35000/67000 = 0.52; 3BHK: 50000/94200 = 0.53 → 3BHK wins
    assert label == "3BHK"
    assert abs(ratio - 50_000 / 94_200) < 0.01


# --- Full score_places integration ---

def test_high_ratio_place_kept():
    place = Place(name="Whitefield", place_type="rental_area",
                  rent_2bhk=35_000, rent_3bhk=50_000,
                  rent_source="https://example.com", drive_minutes=15, kept=True)
    result = score_places([place], _PROJECT, _CFG)
    assert result[0].kept is True
    assert result[0].score_label == "high"


def test_low_ratio_place_dropped():
    place = Place(name="FarAway", place_type="rental_area",
                  rent_2bhk=10_000, rent_3bhk=12_000,
                  rent_source="https://example.com", drive_minutes=10, kept=True)
    result = score_places([place], _PROJECT, _CFG)
    assert result[0].kept is False
    assert result[0].score_label == "low"


def test_it_park_gets_scored():
    place = Place(name="ITPL", place_type="it_park", drive_minutes=20,
                  lat=12.99, lng=77.73, kept=True)
    result = score_places([place], _PROJECT, _CFG)
    assert result[0].score is not None
    assert result[0].kept is True
