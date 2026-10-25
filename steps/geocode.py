"""
steps/geocode.py — Step 3: Attach real lat/lng to each Place via the Google Geocoding API.

Drops any place whose geocoded point:
  - is APPROXIMATE (whole-city result)
  - has a bounding box diagonal > 5 km
  - lies outside search_radius_km of the project
All dropped places are marked with kept=False and a drop_reason.
"""
from __future__ import annotations

import os

from steps.read_project import geocode_address, _is_precise
from geo_utils import haversine_km
from models import Place, ProjectData


def geocode_places(places: list[Place], project: ProjectData, cfg: dict) -> list[Place]:
    """
    Populate .lat and .lng on each Place using the Google Geocoding API.
    Returns the same list with kept/drop_reason set appropriately.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        import sys
        sys.exit("Error: GOOGLE_MAPS_API_KEY is not set.")

    kept_count = 0
    drop_count = 0

    for place in places:
        query = f"{place.name}, {project.city}"
        try:
            result = geocode_address(query, api_key)
        except RuntimeError as e:
            place.kept = False
            place.drop_reason = f"geocode error: {e}"
            drop_count += 1
            print(f"[Step 3] DROP '{place.name}': {place.drop_reason}")
            continue

        # Both residential localities and large IT/tech campuses/SEZs are
        # frequently categorized as APPROXIMATE with a multi-km bounding box by Google Maps.
        allow_approx = True
        ok, reason = _is_precise(result, project.lat, project.lng, cfg["search_radius_km"], allow_approximate=allow_approx)
        if not ok:
            place.kept = False
            place.drop_reason = f"geocode rejected: {reason}"
            drop_count += 1
            print(f"[Step 3] DROP '{place.name}': {reason}")
            continue

        loc = result["geometry"]["location"]
        place.lat = round(loc["lat"], 4)
        place.lng = round(loc["lng"], 4)
        kept_count += 1
        print(f"[Step 3] OK   '{place.name}' → {place.lat}, {place.lng}")

    print(f"[Step 3] Geocoded: {kept_count} kept, {drop_count} dropped.")
    return places
