"""
steps/drive_times.py — Step 4: Fetch peak-hour drive times via Google Distance Matrix API.

- Batches destinations in chunks of 25 (API limit).
- Uses next weekday 08:30 IST as departure time.
- Drops places whose drive time exceeds max_drive_minutes.
"""
from __future__ import annotations

import datetime
import os
import sys

import requests

import cache
from models import Place, ProjectData


_DISTANCE_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
_BATCH_SIZE = 25   # Google's limit per request


def _next_weekday_peak_unix() -> int:
    """Return a Unix timestamp for next weekday 08:30 IST (UTC+5:30)."""
    try:
        import pytz
        tz = pytz.timezone("Asia/Kolkata")
        now = datetime.datetime.now(tz)
    except Exception:
        # Fallback: UTC+5:30 fixed offset
        offset = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now = datetime.datetime.now(offset)

    # Advance to next weekday
    days_ahead = 1
    while True:
        candidate = now + datetime.timedelta(days=days_ahead)
        if candidate.weekday() < 5:  # Mon–Fri
            break
        days_ahead += 1

    peak = candidate.replace(hour=8, minute=30, second=0, microsecond=0)
    return int(peak.timestamp())


def _fetch_batch(
    origin_lat: float,
    origin_lng: float,
    destinations: list[Place],
    departure_time: int,
    api_key: str,
) -> list[float | None]:
    """
    Call the Distance Matrix API for one batch of destinations.
    Returns a list of drive times in minutes (or None on error), one per destination.
    """
    dest_str = "|".join(f"{p.lat},{p.lng}" for p in destinations)
    payload = {
        "origins": f"{origin_lat},{origin_lng}",
        "destinations": dest_str,
        "departure_time": departure_time,
        "traffic_model": "best_guess",
        "mode": "driving",
        "key": api_key,
    }

    cached = cache.get("distance", payload)
    if cached is None:
        resp = requests.get(_DISTANCE_URL, params=payload, timeout=15)
        resp.raise_for_status()
        cached = resp.json()
        cache.set("distance", payload, cached)

    results: list[float | None] = []
    rows = cached.get("rows", [])
    if not rows:
        return [None] * len(destinations)

    elements = rows[0].get("elements", [])
    for elem in elements:
        if elem.get("status") == "OK":
            secs = elem["duration_in_traffic"]["value"]
            results.append(round(secs / 60, 1))
        else:
            results.append(None)

    # Pad if response is shorter than expected
    while len(results) < len(destinations):
        results.append(None)

    return results


def fetch_drive_times(places: list[Place], project: ProjectData, cfg: dict) -> list[Place]:
    """
    Populate .drive_minutes on every kept Place.
    Drops places over max_drive_minutes or with an API error.
    """
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        sys.exit("Error: GOOGLE_MAPS_API_KEY is not set.")

    departure_time = _next_weekday_peak_unix()
    candidates = [p for p in places if p.kept and p.lat is not None]

    kept_count = 0
    drop_count = 0

    for i in range(0, len(candidates), _BATCH_SIZE):
        batch = candidates[i: i + _BATCH_SIZE]
        times = _fetch_batch(project.lat, project.lng, batch, departure_time, api_key)

        for place, minutes in zip(batch, times):
            if minutes is None:
                place.kept = False
                place.drop_reason = "drive time unavailable (API error)"
                drop_count += 1
                print(f"[Step 4] DROP '{place.name}': no drive time from API")
            elif minutes > cfg["max_drive_minutes"]:
                place.kept = False
                place.drop_reason = (
                    f"drive time {minutes:.0f} min > limit {cfg['max_drive_minutes']} min"
                )
                drop_count += 1
                print(f"[Step 4] DROP '{place.name}': {minutes:.0f} min drive")
            else:
                place.drive_minutes = minutes
                kept_count += 1
                print(f"[Step 4] OK   '{place.name}': {minutes:.0f} min drive")

    print(f"[Step 4] Drive times: {kept_count} kept, {drop_count} dropped.")
    return places

