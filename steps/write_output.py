"""
steps/write_output.py — Step 6: Deduplicate, cap, and write both output files.

- Removes overlapping circles of the same type within overlap_threshold_km, keeping the higher score.
- Applies max_targets cap (hard cap at 500 regardless).
- Writes output/google_ads_locations.txt and output/locations_report.csv.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

from geo_utils import haversine_km
from models import Place, ProjectData
from steps.campaign_builder import build_campaign_plan, write_campaign_files


_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent / "output"
_OUTPUT_DIR = _DEFAULT_OUTPUT_DIR
_LOCATIONS_FILE = _OUTPUT_DIR / "google_ads_locations.txt"
_REPORT_FILE = _OUTPUT_DIR / "locations_report.csv"
_KEYWORDS_FILE = _OUTPUT_DIR / "location_keywords.csv"
_HARD_CAP = 500

_REPORT_FIELDS = [
    "name", "type", "lat", "lng", "drive_minutes",
    "rent_2bhk", "rent_3bhk", "rent_source", "rent_date",
    "emi", "ratio", "score", "score_label", "score_reason",
    "kept", "drop_reason", "trending_keywords",
]


import math


def _circle_intersection_area(r1: float, r2: float, d: float) -> float:
    """Return the intersection area (sq km) of two circles with radii r1, r2 and center distance d."""
    if d >= r1 + r2:
        return 0.0
    if d <= abs(r1 - r2):
        return math.pi * (min(r1, r2) ** 2)
    part1 = r1**2 * math.acos((d**2 + r1**2 - r2**2) / (2 * d * r1))
    part2 = r2**2 * math.acos((d**2 + r2**2 - r1**2) / (2 * d * r2))
    part3 = 0.5 * math.sqrt(max(0.0, (-d + r1 + r2) * (d + r1 - r2) * (d - r1 + r2) * (d + r1 + r2)))
    return part1 + part2 - part3


def _deduplicate(places: list[Place], cfg_or_threshold: dict | float) -> list[Place]:
    """
    Remove overlapping circles only when overlap is severe (>= 90% overlap):
    - Partial/moderate circle overlaps are allowed and expected in Google Ads.
    - If two circles overlap by >= 90% (or centers within overlap_threshold_km):
      drop the lower-scoring circle (keeping the higher score / larger radius).
    All places remain in `places` for reporting (locations_report.csv).
    Only non-duplicate targets are marked kept=True for Google Ads targeting.
    """
    if isinstance(cfg_or_threshold, dict):
        r_it = float(cfg_or_threshold.get("radius_km_it_park", 3.0))
        r_rental = float(cfg_or_threshold.get("radius_km_rental", 2.0))
        dist_threshold_km = float(cfg_or_threshold.get("overlap_threshold_km", 1.0))
        overlap_threshold_ratio = float(cfg_or_threshold.get("overlap_threshold_ratio", 0.90))
    else:
        r_it = 3.0
        r_rental = 2.0
        dist_threshold_km = float(cfg_or_threshold)
        overlap_threshold_ratio = 0.90

    def get_radius(p: Place) -> float:
        return r_it if p.place_type == "it_park" else r_rental

    # Sort places: highest score first; if score ties, larger radius first
    candidates = [p for p in places if p.kept and p.lat is not None and p.lng is not None]
    candidates.sort(key=lambda p: (p.score or 0.0, get_radius(p)), reverse=True)

    kept: list[Place] = []
    for candidate in candidates:
        cand_r = get_radius(candidate)
        cand_area = math.pi * (cand_r ** 2)
        overlaps = False

        for existing in kept:
            ex_r = get_radius(existing)
            ex_area = math.pi * (ex_r ** 2)
            dist = haversine_km(existing.lat, existing.lng, candidate.lat, candidate.lng)

            # 1. Very close centers (< 1.0 km)
            if dist < dist_threshold_km:
                overlaps = True
                candidate.kept = False
                candidate.drop_reason = (
                    f"overlaps with '{existing.name}' (distance {dist:.2f} km < {dist_threshold_km:.1f} km threshold)"
                )
                break

            # 2. Severe circular area overlap (>= 90%)
            if dist < (ex_r + cand_r):
                inter = _circle_intersection_area(cand_r, ex_r, dist)
                cand_cov = inter / cand_area
                ex_cov = inter / ex_area
                max_cov = max(cand_cov, ex_cov)

                if max_cov >= (overlap_threshold_ratio - 0.001):
                    overlaps = True
                    candidate.kept = False
                    if ex_r > cand_r:
                        candidate.drop_reason = (
                            f"overlaps with '{existing.name}'; kept larger radius ({max_cov * 100:.0f}% overlap, {dist:.2f} km)"
                        )
                    else:
                        candidate.drop_reason = (
                            f"overlaps with '{existing.name}' ({max_cov * 100:.0f}% area overlap, {dist:.2f} km)"
                        )
                    break

        if not overlaps:
            kept.append(candidate)

    return places


def write_outputs(places: list[Place], project: ProjectData, cfg: dict) -> None:
    """Deduplicate, cap, and write both output files."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Sort kept places by score descending before deduplication
    for p in places:
        if p.score is None and p.kept:
            p.score = 0.0

    places.sort(key=lambda p: (p.kept, p.score or 0.0), reverse=True)

    # Deduplicate
    places = _deduplicate(places, cfg)

    # Collect final kept list and apply cap
    final_kept = [p for p in places if p.kept]
    cap = min(cfg["max_targets"], _HARD_CAP)
    if len(final_kept) > cap:
        for p in final_kept[cap:]:
            p.kept = False
            p.drop_reason = f"exceeded max_targets cap of {cap}"
        final_kept = final_kept[:cap]

    # Project-specific output directory (e.g. output/kunjban/, output/aurelia/, output/vision_flora/)
    name_clean = project.name.lower().strip().replace(" ", "_")
    if name_clean in ("kunjban_society", "kunjban"):
        slug = "kunjban"
    elif name_clean in ("aurelia_heights", "aurelia"):
        slug = "aurelia"
    elif name_clean in ("vision_flora", "vision"):
        slug = "vision_flora"
    else:
        slug = name_clean

    proj_dir = _OUTPUT_DIR / slug
    proj_dir.mkdir(parents=True, exist_ok=True)

    # --- Write google_ads_locations.txt ---
    lines: list[str] = []
    for place in final_kept:
        radius = (
            cfg["radius_km_it_park"]
            if place.place_type == "it_park"
            else cfg["radius_km_rental"]
        )
        lines.append(f"({radius}km:{place.lat:.4f}:{place.lng:.4f})")

    # Write to project-specific folder
    (proj_dir / "google_ads_locations.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[Step 6] Written {len(lines)} targets → {proj_dir / 'google_ads_locations.txt'}")

    # --- Write locations_report.csv ---
    def write_report(dest_path: Path):
        with dest_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_REPORT_FIELDS)
            writer.writeheader()
            for place in places:
                writer.writerow({
                    "name": place.name,
                    "type": place.place_type,
                    "lat": place.lat,
                    "lng": place.lng,
                    "drive_minutes": place.drive_minutes,
                    "rent_2bhk": place.rent_2bhk,
                    "rent_3bhk": place.rent_3bhk,
                    "rent_source": place.rent_source,
                    "rent_date": place.rent_date,
                    "emi": place.emi,
                    "ratio": place.ratio,
                    "score": place.score,
                    "score_label": place.score_label,
                    "score_reason": place.score_reason,
                    "kept": "yes" if place.kept else "no",
                    "drop_reason": place.drop_reason or "",
                    "trending_keywords": "; ".join(place.trending_keywords) if place.trending_keywords else "",
                })

    write_report(proj_dir / "locations_report.csv")
    print(f"[Step 6] Written analysis report ({len(places)} rows) → {proj_dir / 'locations_report.csv'}")

    # --- Write location_keywords.csv ---
    def write_kw_file(dest_path: Path):
        with dest_path.open("w", newline="", encoding="utf-8") as f:
            kw_writer = csv.DictWriter(f, fieldnames=["location_name", "type", "lat", "lng", "keyword"])
            kw_writer.writeheader()
            count = 0
            for place in final_kept:
                for kw in place.trending_keywords:
                    kw_writer.writerow({
                        "location_name": place.name,
                        "type": place.place_type,
                        "lat": place.lat,
                        "lng": place.lng,
                        "keyword": kw,
                    })
                    count += 1
            return count

    kw_count = write_kw_file(proj_dir / "location_keywords.csv")
    print(f"[Step 6] Written {kw_count} keywords → {proj_dir / 'location_keywords.csv'}")

    # --- Generate Campaign A & Campaign B structures ---
    plan = build_campaign_plan(project, places, final_kept, cfg)
    campaign_files_proj = write_campaign_files(plan, proj_dir)

    # For unit tests / backwards compatibility when monkeypatched in test suites
    if _OUTPUT_DIR != _DEFAULT_OUTPUT_DIR or _LOCATIONS_FILE != (_DEFAULT_OUTPUT_DIR / "google_ads_locations.txt"):
        _LOCATIONS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        report_dest = _REPORT_FILE if _REPORT_FILE.parent != _DEFAULT_OUTPUT_DIR else (_OUTPUT_DIR / "locations_report.csv")
        write_report(report_dest)
        kw_dest = _KEYWORDS_FILE if _KEYWORDS_FILE.parent != _DEFAULT_OUTPUT_DIR else (_OUTPUT_DIR / "location_keywords.csv")
        write_kw_file(kw_dest)
        write_campaign_files(plan, _OUTPUT_DIR)

    # --- Write Single Result File: google_ads_input.txt (Locations + Search Keywords) ---
    all_search_keywords = list(dict.fromkeys(
        plan.campaign_a_keywords + [
            kw for p in final_kept for kw in p.trending_keywords
        ]
    ))

    result_lines = [
        "# ============================================================",
        f"# GOOGLE ADS INPUT: LOCATIONS & SEARCH KEYWORDS",
        f"# Project: {project.name} ({project.city})",
        "# ============================================================",
        "",
        "# --- LOCATIONS (Radius Targets for Google Ads) ---",
    ]
    result_lines.extend(lines)
    result_lines.extend([
        "",
        "# --- SEARCH KEYWORDS ---",
    ])
    result_lines.extend(all_search_keywords)

    single_result_file = proj_dir / "google_ads_input.txt"
    single_result_file.write_text("\n".join(result_lines) + "\n", encoding="utf-8")

    # Also provide CSV format for convenient spreadsheet / Editor upload
    with (proj_dir / "google_ads_input.csv").open("w", newline="", encoding="utf-8") as f:
        csv_w = csv.writer(f)
        csv_w.writerow(["Type", "Target / Keyword"])
        for loc in lines:
            csv_w.writerow(["Location", loc])
        for kw in all_search_keywords:
            csv_w.writerow(["Search Keyword", kw])

    print(f"[Step 6] ⭐ Written single Google Ads input file ({len(lines)} locations, {len(all_search_keywords)} keywords) → {single_result_file}")

    # Copy map dashboard if present in output/
    map_src = _OUTPUT_DIR / "campaign_map.html"
    if map_src.exists():
        import shutil
        shutil.copy(map_src, proj_dir / "campaign_map.html")

    print(f"\n✅ Done — {len(final_kept)} targets for '{project.name}' in '{proj_dir.name}/'")
    print(f"   Single Result File : {single_result_file}")
    print(f"   Analysis Report    : {proj_dir / 'locations_report.csv'}")
    print(f"   All Output Files   : {proj_dir}")
