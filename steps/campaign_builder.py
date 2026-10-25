"""
steps/campaign_builder.py — Build 2-Tier Campaign Architecture for Google Ads.

Campaign A: Local Radius
- Locations: Radius circles from this tool (IT parks & rental areas).
- Location Setting: Presence ("People in or regularly in your targeted locations").
- Keywords: Generic real estate keywords ("2 BHK flats", "new apartments", "ready to move flats").

Campaign B: Rest of City / India
- Locations: City (or India) with Campaign A's radius circles explicitly EXCLUDED to prevent overlap/competition.
- Location Setting: Presence or interest ("People in, regularly in, or who've shown interest in your targeted locations").
- Keywords: Must include place names ("flats in Whitefield", "Hoodi apartments", "2 BHK near ITPL").
- Cautions:
  1. City-wide terms ("flats in Bangalore") are broad and expensive. Allocate higher budget/bids to specific terms,
     and lower bids to city-wide terms.
  2. Apply the exact same negative keyword list (rent, PG, resale, jobs, etc.) to both campaigns.
"""
from __future__ import annotations

import csv
from pathlib import Path
from models import CampaignPlan, Place, ProjectData


SHARED_NEGATIVE_KEYWORDS = [
    # Non-buyer transactional intents
    "rent",
    "for rent",
    "rental",
    "to rent",
    "flat on rent",
    "house for rent",
    "PG",
    "paying guest",
    "hostel",
    "room for rent",
    "single room",
    "lease",
    "resale",
    "second hand",
    "used flat",
    "distress sale",
    "broker",
    "brokerage",
    "agent commission",
    "free flat",
    "government quarters",
    "commercial office",
    "office space",
    "coworking",
    "warehouse",
    "industrial plot",
    # Job/Career searchers (especially important near IT parks!)
    "jobs",
    "job vacancy",
    "careers",
    "recruitment",
    "hiring",
    "walk in interview",
    "salary",
    "interview questions",
    "glassdoor",
    "internship",
    # Academic/Informational
    "wiki",
    "wikipedia",
    "syllabus",
    "pincode",
    "pin code",
    "bus route",
    "bus stop",
    "metro station timing",
    "complaints",
    "consumer court",
]


def build_campaign_plan(
    project: ProjectData,
    places: list[Place],
    final_kept: list[Place],
    cfg: dict,
) -> CampaignPlan:
    """Builds the complete Campaign A and Campaign B targeting plan."""
    r_it = float(cfg.get("radius_km_it_park", 3.0))
    r_rental = float(cfg.get("radius_km_rental", 2.0))

    # 1. Campaign A Locations (radius circles)
    campaign_a_locations: list[str] = []
    for p in final_kept:
        r = r_it if p.place_type == "it_park" else r_rental
        campaign_a_locations.append(f"({r:.0f}km:{p.lat:.4f}:{p.lng:.4f})")

    # 2. Campaign A Keywords: Generic ones work here because location radius is already targeted
    unit_labels = [u.unit_type for u in project.unit_emis] or ["2 BHK", "3 BHK"]
    generic_kws: list[str] = []
    for u in unit_labels:
        # Standardize format e.g. "2BHK" -> "2 BHK"
        u_clean = u.replace("BHK", " BHK").strip()
        generic_kws.extend([
            f"{u_clean} flats",
            f"{u_clean} apartments",
            f"{u_clean} flats for sale",
            f"{u_clean} ready to move flats",
            f"buy {u_clean} flat",
        ])
    generic_kws.extend([
        "new apartments",
        "ready to move flats",
        "flats for sale",
        "apartments for sale",
        "luxury apartments for sale",
        "gated community flats",
        "new residential projects",
        "premium apartments",
    ])
    # Deduplicate while preserving order
    campaign_a_keywords = list(dict.fromkeys(generic_kws))

    # 3. Campaign B Locations
    city_name = project.city or "Bengaluru"
    campaign_b_locations = [f"{city_name}, India", "India"]
    campaign_b_excluded = list(campaign_a_locations)  # Exclude Campaign A circles!

    # 4. Campaign B Specific Keywords (Tier 1: Specific Localities & Landmarks)
    specific_kws: list[str] = []

    # Localities from project address & discovered places
    if city_name.lower() in ("bengaluru", "bangalore"):
        localities = ["Whitefield", "Hoodi", "ITPL", "Marathahalli", "Kadugodi", "Hope Farm"]
    else:
        localities = []

    if project.address:
        for part in project.address.replace(",", " ").split():
            part_clean = part.strip()
            if len(part_clean) > 3 and part_clean not in localities and part_clean.lower() != city_name.lower():
                localities.append(part_clean)

    for p in places:
        # Add clean short names
        short_name = p.name.split("(")[0].strip()
        if short_name not in localities:
            localities.append(short_name)
        # Add trending keywords if available
        for kw in p.trending_keywords:
            if kw not in specific_kws:
                specific_kws.append(kw)

    for loc in localities:
        specific_kws.extend([
            f"flats in {loc}",
            f"apartments in {loc}",
            f"{unit_labels[0].replace('BHK', ' BHK')} in {loc}",
            f"{unit_labels[-1].replace('BHK', ' BHK')} in {loc}",
            f"flats near {loc}",
            f"apartments near {loc}",
            f"{loc} apartments",
            f"new projects in {loc}",
            f"buy flat in {loc}",
        ])
    campaign_b_specific = list(dict.fromkeys(specific_kws))

    # 5. Campaign B Broad City Keywords (Tier 2: Broad city-wide terms with lower bids)
    city_aliases = [city_name]
    if city_name.lower() in ("bengaluru", "bangalore"):
        city_aliases = ["Bangalore", "Bengaluru"]

    broad_city_kws: list[str] = []
    for c in city_aliases:
        broad_city_kws.extend([
            f"flats in {c}",
            f"apartments in {c}",
            f"new residential projects in {c}",
            f"luxury apartments in {c}",
            f"gated community flats in {c}",
            f"buy apartment in {c}",
        ])
    campaign_b_broad_city = list(dict.fromkeys(broad_city_kws))

    if city_name.lower() in ("bengaluru", "bangalore"):
        caution_1 = (
            "Caution 1: 'Flats in Bangalore' is broad and expensive. Someone searching that may want "
            "Electronic City or Hebbal, not Whitefield. Give more budget to specific terms ('flats in Whitefield', "
            "'Hoodi apartments', '2 BHK near ITPL') and bid lower (e.g. -40% to -50% CPC) on the city-wide ones."
        )
    else:
        sample_locs = [f"'{l}'" for l in localities[:3]]
        sample_str = ", ".join(sample_locs) if sample_locs else f"'{city_name}'"
        caution_1 = (
            f"Caution 1: 'Flats in {city_name}' is broad and expensive. Give more budget to specific terms "
            f"({sample_str}) and bid lower (e.g. -40% to -50% CPC) on the city-wide ones."
        )

    cautions = [
        caution_1,
        "Caution 2: Add the exact same shared negative keyword list to both campaigns (rent, PG, resale, jobs and so on) so ad spend is never wasted on non-buyers.",
    ]

    return CampaignPlan(
        campaign_a_name=f"{project.name} - Campaign A (Local Radius)",
        campaign_a_setting="Presence",
        campaign_a_locations=campaign_a_locations,
        campaign_a_keywords=campaign_a_keywords,
        campaign_b_name=f"{project.name} - Campaign B (Rest of {city_name} / India)",
        campaign_b_setting="Presence or interest",
        campaign_b_locations=campaign_b_locations,
        campaign_b_excluded_locations=campaign_b_excluded,
        campaign_b_specific_keywords=campaign_b_specific,
        campaign_b_broad_city_keywords=campaign_b_broad_city,
        shared_negatives=SHARED_NEGATIVE_KEYWORDS,
        cautions=cautions,
    )


def write_campaign_files(plan: CampaignPlan, output_dir: Path) -> dict[str, Path]:
    """Writes all campaign files to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    # 1. campaign_a_local_radius.txt
    file_a = output_dir / "campaign_a_local_radius.txt"
    lines_a = [
        f"============================================================",
        f"GOOGLE ADS CAMPAIGN A: LOCAL RADIUS",
        f"============================================================",
        f"Campaign Name: {plan.campaign_a_name}",
        f"Location Option: {plan.campaign_a_setting} ('People in or regularly in your targeted locations')",
        f"",
        f"--- TARGET LOCATIONS (Google Ads Bulk Radius Targets) ---",
    ]
    lines_a.extend(plan.campaign_a_locations)
    lines_a.extend([
        f"",
        f"--- KEYWORDS ({len(plan.campaign_a_keywords)} generic keywords) ---",
        f"# Generic keywords work here because the geographic radius is strictly targeted to tech parks/rental areas.",
    ])
    lines_a.extend(plan.campaign_a_keywords)
    lines_a.extend([
        f"",
        f"--- NEGATIVE KEYWORDS ({len(plan.shared_negatives)} terms) ---",
    ])
    lines_a.extend(plan.shared_negatives)
    file_a.write_text("\n".join(lines_a) + "\n", encoding="utf-8")
    paths["campaign_a"] = file_a

    # 2. campaign_b_rest_of_geo.txt
    file_b = output_dir / "campaign_b_rest_of_geo.txt"
    lines_b = [
        f"============================================================",
        f"GOOGLE ADS CAMPAIGN B: REST OF CITY / INDIA",
        f"============================================================",
        f"Campaign Name: {plan.campaign_b_name}",
        f"Location Option: {plan.campaign_b_setting} ('People in, regularly in, or who have shown interest in your targeted locations')",
        f"",
        f"--- INCLUDED LOCATIONS ---",
        f"{plan.campaign_b_locations[0]} (or India for national buyers/relocators)",
        f"",
        f"--- EXCLUDED LOCATIONS (Prevents competition with Campaign A) ---",
    ]
    lines_b.extend(plan.campaign_b_excluded_locations)
    lines_b.extend([
        f"",
        f"--- TIER 1 KEYWORDS: SPECIFIC LOCALITIES & LANDMARKS (Higher Budget / Higher Bid) ---",
        f"# Must include a place name so you don't pay for people searching in their own city.",
    ])
    lines_b.extend(plan.campaign_b_specific_keywords)
    lines_b.extend([
        f"",
        f"--- TIER 2 KEYWORDS: BROAD CITY-WIDE TERMS (Lower Bids / Cautious Budget) ---",
        f"# Caution: Broad terms ('flats in Bangalore') are expensive and less targeted.",
        f"# Recommendation: Bid 40-50% lower than Tier 1 terms.",
    ])
    lines_b.extend(plan.campaign_b_broad_city_keywords)
    lines_b.extend([
        f"",
        f"--- CAUTIONS ---",
    ])
    for c in plan.cautions:
        lines_b.append(f"- {c}")
    lines_b.extend([
        f"",
        f"--- NEGATIVE KEYWORDS ({len(plan.shared_negatives)} terms) ---",
    ])
    lines_b.extend(plan.shared_negatives)
    file_b.write_text("\n".join(lines_b) + "\n", encoding="utf-8")
    paths["campaign_b"] = file_b

    # 3. negative_keywords.txt
    neg_file = output_dir / "negative_keywords.txt"
    neg_file.write_text("\n".join(plan.shared_negatives) + "\n", encoding="utf-8")
    paths["negative_keywords"] = neg_file

    # 4. google_ads_editor_campaigns.csv
    # Format compatible with Google Ads Editor bulk paste/import
    csv_file = output_dir / "google_ads_editor_campaigns.csv"
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Campaign",
            "Ad Group",
            "Location",
            "Excluded Location",
            "Keyword",
            "Criterion Type",
            "Location Setting",
            "Max CPC",
            "Notes",
        ])

        # Campaign A Locations
        for loc in plan.campaign_a_locations:
            writer.writerow([plan.campaign_a_name, "Locations", loc, "", "", "", plan.campaign_a_setting, "", "Campaign A Radius Target"])

        # Campaign A Keywords
        for kw in plan.campaign_a_keywords:
            writer.writerow([plan.campaign_a_name, "Generic Units", "", "", kw, "Phrase", plan.campaign_a_setting, "Default", "Campaign A Generic Keyword"])

        # Campaign A Negatives
        for neg in plan.shared_negatives:
            writer.writerow([plan.campaign_a_name, "", "", "", neg, "Negative Phrase", "", "", "Shared Negative"])

        # Campaign B Excluded Locations
        for ex_loc in plan.campaign_b_excluded_locations:
            writer.writerow([plan.campaign_b_name, "Locations", "", ex_loc, "", "", plan.campaign_b_setting, "", "Campaign B Excluded (from Campaign A)"])

        # Campaign B Tier 1 Specific Keywords
        for kw in plan.campaign_b_specific_keywords:
            writer.writerow([plan.campaign_b_name, "Geo Specific", "", "", kw, "Phrase", plan.campaign_b_setting, "High", "Tier 1: Specific Locality"])

        # Campaign B Tier 2 Broad City Keywords
        for kw in plan.campaign_b_broad_city_keywords:
            writer.writerow([plan.campaign_b_name, "City Broad (Cautious)", "", "", kw, "Phrase", plan.campaign_b_setting, "Low (-40%)", "Tier 2: Broad City-Wide (Bid Lower)"])

        # Campaign B Negatives
        for neg in plan.shared_negatives:
            writer.writerow([plan.campaign_b_name, "", "", "", neg, "Negative Phrase", "", "", "Shared Negative"])

    paths["editor_csv"] = csv_file
    return paths
