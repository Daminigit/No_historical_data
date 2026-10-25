"""
geo_utils.py — Shared geographic helper functions.
"""
from __future__ import annotations
import math


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in km between two lat/lng points."""
    R = 6_371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def bbox_diagonal_km(northeast_or_south: dict | float, southwest_or_north: dict | float = None, west: float = None, east: float = None) -> float:
    """
    Return the diagonal distance of a bounding box in km.
    Supports:
      - (northeast: dict, southwest: dict)
      - (south: float, north: float, west: float, east: float)
    """
    if isinstance(northeast_or_south, dict):
        ne = northeast_or_south
        sw = southwest_or_north
        return haversine_km(sw["lat"], sw["lng"], ne["lat"], ne["lng"])
    else:
        south = float(northeast_or_south)
        north = float(southwest_or_north)
        return haversine_km(south, float(west), north, float(east))
