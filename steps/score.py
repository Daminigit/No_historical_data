"""
steps/score.py — Step 5: Score each kept Place.

IT parks:  score = linear decay from 10 (0 min) to 1 (max_drive_minutes).
Rental areas: score = ratio band base score × drive-time adjustment.
  ratio = area rent / matching unit EMI (best across available unit types).
  Rental areas with ratio < first band min (0.30 by default) are dropped.
"""
from __future__ import annotations

from models import Place, ProjectData, UnitEMI


def _score_it_park(drive_minutes: float, max_drive_minutes: float) -> float:
    """Linear decay: 10 at 0 min, 1 at max_drive_minutes."""
    return max(1.0, 10.0 - (drive_minutes / max_drive_minutes) * 9.0)


def _band_for_ratio(ratio: float, bands: list[dict]) -> dict:
    """Return the first band whose ratio_max exceeds *ratio*."""
    for band in bands:
        if ratio < band["ratio_max"]:
            return band
    return bands[-1]


def _best_ratio(place: Place, unit_emis: list[UnitEMI]) -> tuple[float | None, float | None, str | None]:
    """
    For a rental area, find the unit type that gives the highest rent/EMI ratio.
    Returns (best_ratio, matching_emi, unit_type_label) or (None, None, None).
    """
    best_ratio = None
    best_emi = None
    best_label = None

    for unit in unit_emis:
        utype_lower = unit.unit_type.lower().replace(" ", "")

        # Match unit type to rent field
        if "2bhk" in utype_lower or "2 bhk" in utype_lower or unit.unit_type == "2BHK":
            rent = place.rent_2bhk
        elif "3bhk" in utype_lower or "3 bhk" in utype_lower or unit.unit_type == "3BHK":
            rent = place.rent_3bhk
        else:
            # Try 2BHK first, then 3BHK as fallback
            rent = place.rent_2bhk or place.rent_3bhk

        if not rent or unit.emi_monthly <= 0:
            continue

        ratio = rent / unit.emi_monthly
        if best_ratio is None or ratio > best_ratio:
            best_ratio = ratio
            best_emi = unit.emi_monthly
            best_label = unit.unit_type

    return best_ratio, best_emi, best_label


def score_places(places: list[Place], project: ProjectData, cfg: dict) -> list[Place]:
    """
    Attach .score, .score_label, .score_reason to every kept Place.
    Drops rental areas whose ratio is below the lowest band's threshold.
    """
    max_drive = cfg["max_drive_minutes"]
    bands = cfg["ratio_bands"]
    low_band = bands[0]  # first band = the "drop" band

    scored = 0
    dropped = 0

    for place in places:
        if not place.kept:
            continue

        if place.drive_minutes is None:
            place.kept = False
            place.drop_reason = "no drive time"
            dropped += 1
            continue

        # --- IT park ---
        if place.place_type == "it_park":
            place.score = round(_score_it_park(place.drive_minutes, max_drive), 2)
            place.score_label = "high" if place.score >= 7 else ("medium" if place.score >= 4 else "low")
            place.score_reason = f"IT park, {place.drive_minutes:.0f} min drive"
            scored += 1

        # --- Rental area ---
        elif place.place_type == "rental_area":
            ratio, emi, unit_label = _best_ratio(place, project.unit_emis)

            if ratio is None:
                place.kept = False
                place.drop_reason = "no rent data matches any available unit type"
                dropped += 1
                print(f"[Step 5] DROP '{place.name}': no matching rent data")
                continue

            band = _band_for_ratio(ratio, bands)

            if band["label"] == "low":
                if place.drive_minutes is not None and place.drive_minutes <= 3.0:
                    place.score = 5.0
                    place.score_label = "medium"
                    place.score_reason = f"Immediate project locality ({place.drive_minutes:.0f} min drive) — key local resident catchment"
                    place.ratio = round(ratio, 4)
                    place.emi = round(emi, 0)
                    scored += 1
                else:
                    place.kept = False
                    place.drop_reason = (
                        f"ratio {ratio:.2f} < {low_band['ratio_max']} — renters likely can't afford this project"
                    )
                    dropped += 1
                    # Still record the ratio for the report
                    place.ratio = round(ratio, 4)
                    place.emi = round(emi, 0)
                    place.score_label = "low"
                    print(f"[Step 5] DROP '{place.name}': ratio {ratio:.2f} → low score")
                    continue

            # Drive-time adjustment (±30%)
            drive_factor = 1.0 - 0.3 * (place.drive_minutes / max_drive)
            adjusted_score = round(band["score"] * drive_factor, 2)

            place.ratio = round(ratio, 4)
            place.emi = round(emi, 0)
            place.score = adjusted_score
            place.score_label = band["label"]
            place.score_reason = (
                f"rent/EMI ratio {ratio:.2f} ({unit_label}), "
                f"{place.drive_minutes:.0f} min drive → {band['label']}"
            )
            scored += 1

    print(f"[Step 5] Scored: {scored} places, {dropped} dropped.")
    return places
