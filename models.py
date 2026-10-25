"""
models.py — Shared dataclasses for the Location List Builder.
"""
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class UnitEMI:
    """EMI derived from one available unit type in the project JSON."""
    unit_type: str          # e.g. "2BHK", "3BHK"
    price_min_inr: float    # lowest listed price for this type
    emi_monthly: float      # computed monthly EMI (₹)


@dataclass
class Place:
    """
    A candidate location — either an IT park or a rental area.
    Fields are populated progressively as the pipeline runs.
    """
    name: str
    place_type: str                 # "it_park" | "rental_area"

    # Populated by Step 3 (geocode)
    lat: float | None = None
    lng: float | None = None

    # Populated by Step 4 (drive times)
    drive_minutes: float | None = None

    # Populated by Step 2 (LLM) — rental areas only
    rent_2bhk: float | None = None
    rent_3bhk: float | None = None
    rent_source: str | None = None
    rent_date: str | None = None

    # Populated by Step 5 (score)
    emi: float | None = None        # EMI of the best-matching unit type
    ratio: float | None = None      # rent / emi
    score: float | None = None
    score_label: str | None = None  # "low" | "medium" | "high"
    score_reason: str | None = None

    # Final disposition
    kept: bool = True
    drop_reason: str | None = None

    # Trending search keywords (populated by Step 2)
    trending_keywords: list[str] = field(default_factory=list)


@dataclass
class ProjectData:
    """Parsed and validated data from the project info JSON."""
    name: str
    lat: float
    lng: float
    city: str
    address: str
    unit_emis: list[UnitEMI] = field(default_factory=list)


@dataclass
class CampaignPlan:
    """Complete 2-tier campaign architecture for Google Ads."""
    campaign_a_name: str
    campaign_a_setting: str
    campaign_a_locations: list[str]
    campaign_a_keywords: list[str]

    campaign_b_name: str
    campaign_b_setting: str
    campaign_b_locations: list[str]
    campaign_b_excluded_locations: list[str]
    campaign_b_specific_keywords: list[str]
    campaign_b_broad_city_keywords: list[str]

    shared_negatives: list[str] = field(default_factory=list)
    cautions: list[str] = field(default_factory=list)

