"""tests/test_output_format.py — Validate the exact format of google_ads_locations.txt."""
import re
import pytest
from pathlib import Path

from models import Place, ProjectData
from steps.write_output import write_outputs

_LINE_RE = re.compile(r"^\(\d+km:-?\d+\.\d{4}:-?\d+\.\d{4}\)$")

_CFG = {
    "radius_km_it_park": 3,
    "radius_km_rental": 2,
    "max_targets": 50,
    "overlap_threshold_km": 1.0,
}

_PROJECT = ProjectData(
    name="Test Project", lat=12.98, lng=77.72, city="Bengaluru", address="Whitefield"
)


def _make_places():
    return [
        Place(name="ITPL", place_type="it_park",
              lat=12.9763, lng=77.7278, drive_minutes=10, score=9.0, kept=True),
        Place(name="Whitefield", place_type="rental_area",
              lat=12.9698, lng=77.7500, drive_minutes=15, score=8.5, kept=True,
              rent_source="https://example.com", rent_2bhk=35000, emi=67000, ratio=0.52),
        Place(name="Marathahalli", place_type="rental_area",
              lat=12.9591, lng=77.6972, drive_minutes=25, score=7.0, kept=True,
              rent_source="https://example.com", rent_2bhk=30000, emi=67000, ratio=0.45),
    ]


def test_all_lines_match_format(tmp_path, monkeypatch):
    """Every line in google_ads_locations.txt must match the exact regex."""
    # Redirect output dir to tmp_path
    import steps.write_output as wo
    monkeypatch.setattr(wo, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(wo, "_LOCATIONS_FILE", tmp_path / "google_ads_locations.txt")
    monkeypatch.setattr(wo, "_REPORT_FILE", tmp_path / "locations_report.csv")

    places = _make_places()
    write_outputs(places, _PROJECT, _CFG)

    content = (tmp_path / "google_ads_locations.txt").read_text()
    lines = [ln for ln in content.splitlines() if ln.strip()]
    assert lines, "Output file is empty"
    for line in lines:
        assert _LINE_RE.match(line), f"Line does not match format: '{line}'"


def test_no_spaces_in_output(tmp_path, monkeypatch):
    import steps.write_output as wo
    monkeypatch.setattr(wo, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(wo, "_LOCATIONS_FILE", tmp_path / "google_ads_locations.txt")
    monkeypatch.setattr(wo, "_REPORT_FILE", tmp_path / "locations_report.csv")

    write_outputs(_make_places(), _PROJECT, _CFG)
    content = (tmp_path / "google_ads_locations.txt").read_text()
    for line in content.splitlines():
        assert " " not in line, f"Space found in line: '{line}'"


def test_coordinates_have_four_decimal_places(tmp_path, monkeypatch):
    import steps.write_output as wo
    monkeypatch.setattr(wo, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(wo, "_LOCATIONS_FILE", tmp_path / "google_ads_locations.txt")
    monkeypatch.setattr(wo, "_REPORT_FILE", tmp_path / "locations_report.csv")

    write_outputs(_make_places(), _PROJECT, _CFG)
    content = (tmp_path / "google_ads_locations.txt").read_text()
    for line in content.splitlines():
        if not line.strip():
            continue
        parts = line.strip("()").split(":")
        # parts = ["3km", "12.9763", "77.7278"]
        for coord in parts[1:]:
            decimal_part = coord.split(".")[-1].lstrip("-")
            assert len(decimal_part) == 4, f"Expected 4 d.p. in '{coord}' (line: '{line}')"


def test_max_targets_cap_respected(tmp_path, monkeypatch):
    import steps.write_output as wo
    monkeypatch.setattr(wo, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(wo, "_LOCATIONS_FILE", tmp_path / "google_ads_locations.txt")
    monkeypatch.setattr(wo, "_REPORT_FILE", tmp_path / "locations_report.csv")

    # Create 10 well-spaced places, cap at 2
    places = [
        Place(name=f"Park {i}", place_type="it_park",
              lat=round(12.98 + i * 0.05, 4), lng=77.72,
              drive_minutes=10, score=10.0 - i, kept=True)
        for i in range(10)
    ]
    cfg = {**_CFG, "max_targets": 2}
    write_outputs(places, _PROJECT, cfg)

    content = (tmp_path / "google_ads_locations.txt").read_text()
    lines = [ln for ln in content.splitlines() if ln.strip()]
    assert len(lines) == 2


def test_keywords_output_generated(tmp_path, monkeypatch):
    import steps.write_output as wo
    monkeypatch.setattr(wo, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(wo, "_LOCATIONS_FILE", tmp_path / "google_ads_locations.txt")
    monkeypatch.setattr(wo, "_REPORT_FILE", tmp_path / "locations_report.csv")
    monkeypatch.setattr(wo, "_KEYWORDS_FILE", tmp_path / "location_keywords.csv")

    # Use two non-overlapping places to test keyword writing
    places = [
        Place(
            name="ITPL", place_type="it_park",
            lat=12.9763, lng=77.7278, drive_minutes=10, score=9.0, kept=True,
            trending_keywords=["flats near ITPL", "apartments near ITPL"]
        ),
        Place(
            name="Electronic City", place_type="rental_area",
            lat=12.8452, lng=77.6602, drive_minutes=35, score=8.5, kept=True,
            rent_source="https://example.com", rent_2bhk=35000, emi=67000, ratio=0.52,
            trending_keywords=["flats for sale in Electronic City"]
        ),
    ]

    write_outputs(places, _PROJECT, _CFG)

    kw_file = tmp_path / "location_keywords.csv"
    assert kw_file.exists()
    kw_content = kw_file.read_text()
    assert "flats near ITPL" in kw_content
    assert "flats for sale in Electronic City" in kw_content

    report_content = (tmp_path / "locations_report.csv").read_text()
    assert "trending_keywords" in report_content
    assert "flats near ITPL; apartments near ITPL" in report_content


def test_cross_type_overlap_dropped(tmp_path, monkeypatch):
    """When a place circle overlaps an existing larger-radius circle, the smaller-radius circle is dropped."""
    import steps.write_output as wo
    monkeypatch.setattr(wo, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(wo, "_LOCATIONS_FILE", tmp_path / "google_ads_locations.txt")
    monkeypatch.setattr(wo, "_REPORT_FILE", tmp_path / "locations_report.csv")
    monkeypatch.setattr(wo, "_KEYWORDS_FILE", tmp_path / "location_keywords.csv")

    # ITPL (it_park, radius 5km) and Hoodi (rental_area, radius 3km) are 2.52 km apart
    # ITPL has larger radius (5km vs 3km), so Hoodi is dropped
    places = [
        Place(
            name="ITPL", place_type="it_park",
            lat=12.9858, lng=77.7356, drive_minutes=10, score=8.5, kept=True,
        ),
        Place(
            name="Hoodi", place_type="rental_area",
            lat=12.9896, lng=77.7127, drive_minutes=12, score=4.7, kept=True,
            rent_source="https://example.com", rent_2bhk=28000, emi=67000, ratio=0.45,
        ),
    ]
    cfg = {
        "radius_km_it_park": 5.0,
        "radius_km_rental": 3.0,
        "max_targets": 50,
        "overlap_threshold_km": 1.0,
    }

    write_outputs(places, _PROJECT, cfg)

    # ITPL should be kept, Hoodi dropped because ITPL has the larger radius
    itpl_place = [p for p in places if p.name == "ITPL"][0]
    hoodi_place = [p for p in places if p.name == "Hoodi"][0]
    assert itpl_place.kept is True
    assert hoodi_place.kept is False
    assert "kept larger radius" in hoodi_place.drop_reason

    # google_ads_locations.txt should only have 1 target
    content = (tmp_path / "google_ads_locations.txt").read_text()
    lines = [ln for ln in content.splitlines() if ln.strip()]
    assert len(lines) == 1
    assert "12.9858:77.7356" in lines[0]


def test_non_overlapping_cross_type_kept(tmp_path, monkeypatch):
    """When places do not almost fully overlap, both are kept."""
    import steps.write_output as wo
    monkeypatch.setattr(wo, "_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(wo, "_LOCATIONS_FILE", tmp_path / "google_ads_locations.txt")
    monkeypatch.setattr(wo, "_REPORT_FILE", tmp_path / "locations_report.csv")

    places = [
        Place(
            name="Whitefield", place_type="rental_area",
            lat=12.9698, lng=77.7500, drive_minutes=15, score=9.0, kept=True,
            rent_source="https://example.com", rent_2bhk=35000, emi=67000, ratio=0.52,
        ),
        Place(
            name="Electronic City", place_type="it_park",
            lat=12.8452, lng=77.6602, drive_minutes=35, score=8.0, kept=True,
        ),
    ]
    cfg = {
        "radius_km_it_park": 5.0,
        "radius_km_rental": 3.0,
        "max_targets": 50,
        "overlap_threshold_km": 1.0,
        "overlap_threshold_ratio": 0.65,
    }

    write_outputs(places, _PROJECT, cfg)
    assert places[0].kept is True
    assert places[1].kept is True
    content = (tmp_path / "google_ads_locations.txt").read_text()
    lines = [ln for ln in content.splitlines() if ln.strip()]
    assert len(lines) == 2
