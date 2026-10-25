"""
tests/test_campaigns.py — Unit tests for Campaign A and Campaign B targeting architecture.
"""
import pytest
from pathlib import Path
from models import Place, ProjectData, UnitEMI
from steps.campaign_builder import build_campaign_plan, write_campaign_files, SHARED_NEGATIVE_KEYWORDS


@pytest.fixture
def sample_project():
    return ProjectData(
        name="Aurelia Heights",
        lat=12.9800,
        lng=77.7200,
        city="Bengaluru",
        address="Hoodi, Whitefield, Bengaluru",
        unit_emis=[
            UnitEMI(unit_type="2BHK", price_min_inr=9600000, emi_monthly=66649),
            UnitEMI(unit_type="3BHK", price_min_inr=13500000, emi_monthly=93725),
        ],
    )


@pytest.fixture
def sample_places():
    return [
        Place(
            name="ITPL",
            place_type="it_park",
            lat=12.9858,
            lng=77.7356,
            score=8.5,
            kept=True,
            trending_keywords=["flats near ITPL", "2 BHK near ITPL"],
        ),
        Place(
            name="Prestige Tech Park",
            place_type="it_park",
            lat=12.9423,
            lng=77.6936,
            score=4.7,
            kept=True,
            trending_keywords=["apartments near Prestige Tech Park"],
        ),
        Place(
            name="Whitefield",
            place_type="rental_area",
            lat=12.9698,
            lng=77.7500,
            score=9.1,
            kept=False,
            drop_reason="overlaps with ITPL",
            trending_keywords=["flats in Whitefield"],
        ),
    ]


@pytest.fixture
def sample_cfg():
    return {
        "radius_km_it_park": 3.0,
        "radius_km_rental": 2.0,
    }


def test_campaign_a_presence_and_generic_keywords(sample_project, sample_places, sample_cfg):
    final_kept = [p for p in sample_places if p.kept]
    plan = build_campaign_plan(sample_project, sample_places, final_kept, sample_cfg)

    # 1. Setting must be Presence
    assert plan.campaign_a_setting == "Presence"

    # 2. Locations must match kept circles
    assert len(plan.campaign_a_locations) == 2
    assert "(3km:12.9858:77.7356)" in plan.campaign_a_locations
    assert "(3km:12.9423:77.6936)" in plan.campaign_a_locations

    # 3. Keywords must include generic ones
    assert any("2 BHK flats" in kw for kw in plan.campaign_a_keywords)
    assert any("new apartments" in kw for kw in plan.campaign_a_keywords)
    assert any("ready to move flats" in kw for kw in plan.campaign_a_keywords)


def test_campaign_b_presence_or_interest_and_exclusions(sample_project, sample_places, sample_cfg):
    final_kept = [p for p in sample_places if p.kept]
    plan = build_campaign_plan(sample_project, sample_places, final_kept, sample_cfg)

    # 1. Setting must be Presence or interest
    assert plan.campaign_b_setting == "Presence or interest"

    # 2. Excluded locations must equal Campaign A's circles
    assert plan.campaign_b_excluded_locations == plan.campaign_a_locations
    assert "(3km:12.9858:77.7356)" in plan.campaign_b_excluded_locations

    # 3. Campaign B specific keywords must include place names
    for kw in plan.campaign_b_specific_keywords:
        assert any(term.lower() in kw.lower() for term in ["whitefield", "hoodi", "itpl", "marathahalli", "prestige", "kadugodi", "hope farm"]), (
            f"Keyword '{kw}' does not include a specific place name"
        )

    # 4. Bare generic keywords like '2 BHK flats' must NOT be in Campaign B specific keywords
    assert "2 BHK flats" not in plan.campaign_b_specific_keywords
    assert "new apartments" not in plan.campaign_b_specific_keywords

    # 5. Broad city keywords exist and cautions are documented
    assert any("Bangalore" in kw or "Bengaluru" in kw for kw in plan.campaign_b_broad_city_keywords)
    assert any("broad and expensive" in c for c in plan.cautions)


def test_shared_negative_keywords(sample_project, sample_places, sample_cfg):
    final_kept = [p for p in sample_places if p.kept]
    plan = build_campaign_plan(sample_project, sample_places, final_kept, sample_cfg)

    # Negatives list must contain rent, PG, resale, jobs, etc.
    assert "rent" in plan.shared_negatives
    assert "PG" in plan.shared_negatives
    assert "resale" in plan.shared_negatives
    assert "jobs" in plan.shared_negatives


def test_write_campaign_files(tmp_path, sample_project, sample_places, sample_cfg):
    final_kept = [p for p in sample_places if p.kept]
    plan = build_campaign_plan(sample_project, sample_places, final_kept, sample_cfg)
    paths = write_campaign_files(plan, tmp_path)

    # Verify all files are created
    assert paths["campaign_a"].exists()
    assert paths["campaign_b"].exists()
    assert paths["negative_keywords"].exists()
    assert paths["editor_csv"].exists()

    content_a = paths["campaign_a"].read_text()
    assert "Presence" in content_a
    assert "(3km:12.9858:77.7356)" in content_a

    content_b = paths["campaign_b"].read_text()
    assert "Presence or interest" in content_b
    assert "EXCLUDED LOCATIONS" in content_b
    assert "(3km:12.9858:77.7356)" in content_b

    content_csv = paths["editor_csv"].read_text()
    assert "Campaign A" in content_csv
    assert "Campaign B" in content_csv
    assert "Negative Phrase" in content_csv
