"""
steps/read_project.py — Step 1: Parse the project info JSON and compute unit EMIs.

Responsibilities:
- Validate required fields.
- Resolve lat/lng from address via Google Geocoding API if not provided.
- Abort clearly if the address resolves to a city/region rather than a precise point.
- Compute monthly EMI for every available unit type.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import requests

import cache
from geo_utils import bbox_diagonal_km, haversine_km
from models import ProjectData, UnitEMI


# ---------------------------------------------------------------------------
# EMI calculation
# ---------------------------------------------------------------------------

def compute_emi(price_inr: float, cfg: dict) -> float:
    """Return the monthly EMI (₹) for a home at *price_inr*."""
    loan = price_inr * (1 - cfg["down_payment_pct"] / 100)
    r = (cfg["interest_rate_pct"] / 100) / 12
    n = cfg["tenure_years"] * 12
    return loan * r * (1 + r) ** n / ((1 + r) ** n - 1)


# ---------------------------------------------------------------------------
# Geocoding helper (also used by geocode.py for individual places)
# ---------------------------------------------------------------------------

_GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_CITY_BBOX_KM = 5.0   # bounding boxes larger than this are rejected as too vague


def geocode_address(query: str, api_key: str) -> dict:
    """
    Call the Google Geocoding API for *query*.
    Returns the first result dict (with geometry, types, etc.) or raises RuntimeError.
    Responses are cached.
    """
    if not api_key:
        raise RuntimeError("GOOGLE_MAPS_API_KEY is not set.")

    cached = cache.get("geocode", query)
    if cached is not None:
        return cached

    resp = requests.get(
        _GEOCODING_URL,
        params={"address": query, "key": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") != "OK" or not data.get("results"):
        raise RuntimeError(f"Google Geocoding failed for '{query}': {data.get('status')}")

    result = data["results"][0]
    cache.set("geocode", query, result)
    return result


def _is_precise(result: dict, project_lat: float | None, project_lng: float | None,
                search_radius_km: float, allow_approximate: bool = False) -> tuple[bool, str]:
    """
    Return (True, "") if *result* is a precise, usable point, else (False, reason).
    """
    geometry = result["geometry"]
    location_type = geometry.get("location_type", "")
    viewport = geometry.get("viewport", {})

    # Reject APPROXIMATE results (city/region level) unless explicitly allowed for localities
    if location_type == "APPROXIMATE" and not allow_approximate:
        return False, f"location_type is APPROXIMATE"

    # Reject results with a very large bounding box (whole-city matches)
    max_bbox = 12.0 if allow_approximate else _CITY_BBOX_KM
    if viewport:
        ne = viewport.get("northeast", {})
        sw = viewport.get("southwest", {})
        if ne and sw:
            diagonal = bbox_diagonal_km(ne, sw)
            if diagonal > max_bbox:
                return False, f"bounding box too large ({diagonal:.1f} km diagonal)"

    # If we already know the project location, reject points too far away
    if project_lat is not None and project_lng is not None:
        loc = geometry["location"]
        dist = haversine_km(project_lat, project_lng, loc["lat"], loc["lng"])
        if dist > search_radius_km:
            return False, f"resolved point is {dist:.1f} km from project (limit {search_radius_km} km)"

    return True, ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def read_project(project_path: str, cfg: dict) -> ProjectData:
    """
    Parse *project_path* (a project info JSON) and return a populated ProjectData.
    Aborts with a clear message if the location cannot be resolved to a precise point.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")

    with open(project_path, encoding="utf-8") as f:
        raw: dict[str, Any] = json.load(f)

    # --- Required top-level fields ---
    project_dict = raw.get("project")
    if isinstance(project_dict, dict):
        project_name = project_dict.get("name")
    elif project_dict is not None:
        project_name = str(project_dict)
    else:
        project_name = None

    project_name = project_name or raw.get("name") or raw.get("project_name") or raw.get("title")
    if not project_name:
        sys.exit("Error: project.name is missing from the project JSON.")

    location = raw.get("location") if isinstance(raw.get("location"), dict) else {}
    city = location.get("city") or raw.get("city") or ""
    address = location.get("address") or raw.get("address") or ""

    lat = location.get("lat") or location.get("latitude") or raw.get("lat") or raw.get("latitude")
    lng = location.get("lng") or location.get("longitude") or raw.get("lng") or raw.get("longitude")

    # --- Resolve coordinates ---
    if lat and lng:
        lat, lng = float(lat), float(lng)
        print(f"[Step 1] Using provided coordinates: {lat:.4f}, {lng:.4f}")
    else:
        if not api_key:
            sys.exit("Error: GOOGLE_MAPS_API_KEY is not set and no lat/lng in the project JSON.")
        query = f"{address}, {city}".strip(", ")
        if not query:
            sys.exit("Error: No lat/lng and no address/city in the project JSON.")
        print(f"[Step 1] No lat/lng found. Geocoding '{query}' …")
        try:
            result = geocode_address(query, api_key)
        except RuntimeError as e:
            sys.exit(f"Error: {e}")

        ok, reason = _is_precise(result, None, None, cfg["search_radius_km"])
        if not ok:
            sys.exit(
                f"Error: address '{query}' resolves to a city or region ({reason}).\n"
                "Please add precise lat/lng to the project JSON."
            )
        loc = result["geometry"]["location"]
        lat, lng = round(loc["lat"], 4), round(loc["lng"], 4)
        print(f"[Step 1] Geocoded to: {lat}, {lng}")

    # --- Extract available units and compute EMI ---
    units_raw = raw.get("units") or raw.get("configurations") or raw.get("unit_types") or []
    unit_emis: list[UnitEMI] = []
    for unit in units_raw:
        status = str(unit.get("status", "")).lower().strip()
        # If status is explicitly given as unavailable/sold, skip
        if status in ("sold", "sold_out", "unavailable", "booked"):
            continue
        price = (
            unit.get("price_min_inr")
            or unit.get("price_min")
            or unit.get("price_inr")
            or unit.get("price")
            or unit.get("min_price")
        )
        utype = (
            unit.get("type")
            or unit.get("unit_type")
            or unit.get("configuration")
            or unit.get("config")
            or unit.get("name")
        )
        if not price or not utype:
            continue
        emi = compute_emi(float(price), cfg)
        unit_emis.append(UnitEMI(unit_type=str(utype), price_min_inr=float(price), emi_monthly=emi))
        print(f"[Step 1] {utype}: price ₹{price:,.0f} → EMI ₹{emi:,.0f}/mo")

    if not unit_emis:
        sys.exit(
            "Error: No available units with a price found in the project JSON. "
            "Cannot compute EMI for rental scoring."
        )

    return ProjectData(
        name=project_name,
        lat=lat,
        lng=lng,
        city=city or address,
        address=address,
        unit_emis=unit_emis,
    )
