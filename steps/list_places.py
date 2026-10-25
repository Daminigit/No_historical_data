"""
steps/list_places.py — Step 2: Ask an LLM to discover
IT parks and rental areas near the project.

Supported LLM providers (set LLM_PROVIDER in .env):
  - "groq"   (default) — uses GROQ_API_KEY + GROQ_MODEL
  - "gemini"            — uses GEMINI_API_KEY + GEMINI_MODEL

Key rule: the LLM supplies names, rents, and source URLs ONLY.
Any coordinate-like fields returned by the LLM are stripped before creating Place objects.
"""
from __future__ import annotations

import json
import os
import re
import sys

import cache
from models import Place, ProjectData


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_PROMPT = """\
You are a real estate market researcher for India.

Project address: {address}, {city}
Search radius: {radius} km

=== Task 1 — IT parks ===
List 5 to 8 major IT/tech parks, SEZs, and large office campuses within {radius} km of the project address.
CRITICAL: Only list employment hubs that workers at this specific project address ({address}) would realistically commute to on a daily basis (do NOT list hubs on the completely opposite side of a large metro city).
For each return:
  - name
  - trending_keywords: list of 3-5 popular Google search terms people use when looking for homes/apartments near this tech park (e.g. "flats near <Name>", "apartments near <Name>", "2 BHK near <Name>")
Do NOT include coordinates, distances, or drive times.

=== Task 2 — Rental areas ===
List 5 to 8 prominent residential localities within {radius} km of the project address where people rent homes and would realistically consider buying in the project's neighborhood or shared commuter corridor.
CRITICAL: Prioritize adjacent localities and direct feeder neighborhoods around {address}. Avoid distant localities across town.
For each locality return:
  - name
  - typical current monthly rent for a 2 BHK apartment in a gated society (₹, integer)
  - typical current monthly rent for a 3 BHK apartment in a gated society (₹, integer)
  - source_url: real estate portal reference URL or listing URL (e.g. from magicbricks.com, 99acres.com, housing.com, or nobroker.in)
  - source_date: the date or "current"
  - trending_keywords: list of 3-5 popular Google search terms people use when looking for homes/apartments to buy in this area (e.g. "flats for sale in <Locality>", "apartments in <Locality>", "3 BHK in <Locality>")
=== Guidelines for Names ===
- Use standard, clean locality and business park names recognizable in {city} (e.g. "Rajiv Gandhi Infotech Park Hinjewadi", "Wakad", "Bhosari MIDC", "Pimple Nilakh", "Baner", "Talawade IT Park").
- Avoid overly broad municipal names that represent entire regions/cities (e.g. do not just return "Pimpri-Chinchwad" or "Pune").
- Do NOT include coordinates or distances.

=== Output format ===
Return ONLY a JSON object — no markdown, no extra text — with this exact structure:
{{
  "it_parks": [
    {{
      "name": "ITPL",
      "trending_keywords": ["flats near ITPL", "apartments near ITPL", "2 BHK near ITPL"]
    }}
  ],
  "rental_areas": [
    {{
      "name": "Whitefield",
      "rent_2bhk": 30000,
      "rent_3bhk": 45000,
      "source_url": "https://example.com/...",
      "source_date": "2024-11-01",
      "trending_keywords": ["flats for sale in Whitefield", "apartments in Whitefield"]
    }}
  ]
}}
"""


# ---------------------------------------------------------------------------
# LLM backends
# ---------------------------------------------------------------------------

def _call_groq(prompt: str) -> str:
    """Call the Groq API and return the raw text response."""
    model_name = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        sys.exit(
            "Error: GROQ_API_KEY is not set. "
            "Set it in .env, or switch to Gemini by setting LLM_PROVIDER=gemini and GEMINI_API_KEY."
        )
    try:
        from groq import Groq
    except ImportError:
        sys.exit("Error: groq package is not installed. Run: pip install groq")

    client = Groq(api_key=api_key)
    max_tokens = int(os.environ.get("GROQ_MAX_TOKENS", "1600"))
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=model_name,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return chat_completion.choices[0].message.content.strip()


def _call_gemini(prompt: str) -> str:
    """Call the Google Gemini API and return the raw text response."""
    model_name = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        sys.exit(
            "Error: GEMINI_API_KEY is not set. "
            "Set it in .env, or switch to Groq by setting LLM_PROVIDER=groq and GROQ_API_KEY."
        )
    try:
        import google.generativeai as genai
    except ImportError:
        sys.exit(
            "Error: google-generativeai package is not installed. "
            "Run: pip install google-generativeai"
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config=genai.GenerationConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    response = model.generate_content(prompt)
    return response.text.strip()


def _call_llm(prompt: str) -> str:
    """
    Dispatch to the configured LLM provider.
    Reads LLM_PROVIDER from env (default: "groq").
    Caches the response so re-runs are free.
    """
    cached = cache.get("llm", prompt)
    if cached is not None:
        return cached

    provider = os.environ.get("LLM_PROVIDER", "groq").lower().strip()
    print(f"[Step 2] Using LLM provider: {provider}")

    if provider == "gemini":
        text = _call_gemini(prompt)
    elif provider == "groq":
        text = _call_groq(prompt)
    else:
        sys.exit(
            f"Error: Unknown LLM_PROVIDER '{provider}'. "
            "Supported values: 'groq', 'gemini'."
        )

    cache.set("llm", prompt, text)
    return text


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

_LAT_LNG_PATTERN = re.compile(
    r'"(lat|lng|latitude|longitude|coordinates?|location)"\s*:\s*-?\d+',
    re.IGNORECASE,
)


def _strip_coordinate_fields(obj: dict) -> dict:
    """
    Recursively remove any dict keys that look like coordinate fields.
    Logs a warning for each field stripped.
    """
    bad_keys = {"lat", "lng", "latitude", "longitude", "coordinates", "location",
                "distance_km", "drive_minutes", "drive_time"}
    cleaned = {}
    for k, v in obj.items():
        if k.lower() in bad_keys:
            print(f"[Step 2] WARNING: LLM returned a coordinate-like field '{k}' — stripped.")
            continue
        cleaned[k] = v
    return cleaned


def _parse_response(text: str) -> tuple[list[dict], list[dict]]:
    """
    Extract JSON from the LLM response and return (it_parks, rental_areas).
    Falls back to an empty list on parse errors (with a warning).
    """
    # Strip markdown fences if present
    text = re.sub(r"^```[a-z]*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"[Step 2] WARNING: Could not parse LLM response as JSON: {e}")
        print(f"[Step 2] Raw response (first 500 chars): {text[:500]}")
        return [], []

    it_parks_raw = data.get("it_parks", [])
    rental_raw = data.get("rental_areas", [])

    # Strip any coordinate fields the LLM sneaked in
    it_parks = [_strip_coordinate_fields(p) for p in it_parks_raw]
    rental_areas = [_strip_coordinate_fields(p) for p in rental_raw]

    # Filter rental areas that lack a source URL
    sourced = []
    for area in rental_areas:
        if not area.get("source_url"):
            print(f"[Step 2] Dropping '{area.get('name', '?')}' — no source URL.")
            continue
        if not (area.get("rent_2bhk") or area.get("rent_3bhk")):
            print(f"[Step 2] Dropping '{area.get('name', '?')}' — no rent figures.")
            continue
        sourced.append(area)

    return it_parks, sourced


def _extract_keywords(item: dict) -> list[str]:
    raw_kw = item.get("trending_keywords") or item.get("keywords") or []
    if isinstance(raw_kw, str):
        return [k.strip() for k in re.split(r"[,;\n]", raw_kw) if k.strip()]
    elif isinstance(raw_kw, list):
        return [str(k).strip() for k in raw_kw if str(k).strip()]
    return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def list_places(project: ProjectData, cfg: dict) -> list[Place]:
    """
    Call the LLM to discover IT parks and rental areas near *project*.
    Returns a list of Place objects with rents and source URLs (no coordinates yet).
    """
    prompt = _PROMPT.format(
        address=project.address,
        city=project.city,
        radius=cfg["search_radius_km"],
    )

    print(f"[Step 2] Querying LLM for places near {project.city} …")
    raw_text = _call_llm(prompt)
    it_parks, rental_areas = _parse_response(raw_text)

    places: list[Place] = []

    for p in it_parks:
        name = p.get("name", "").strip()
        if name:
            places.append(Place(
                name=name,
                place_type="it_park",
                trending_keywords=_extract_keywords(p),
            ))

    for r in rental_areas:
        name = r.get("name", "").strip()
        if name:
            places.append(Place(
                name=name,
                place_type="rental_area",
                rent_2bhk=float(r["rent_2bhk"]) if r.get("rent_2bhk") else None,
                rent_3bhk=float(r["rent_3bhk"]) if r.get("rent_3bhk") else None,
                rent_source=r.get("source_url"),
                rent_date=r.get("source_date"),
                trending_keywords=_extract_keywords(r),
            ))

    print(f"[Step 2] Found {sum(1 for p in places if p.place_type == 'it_park')} IT parks, "
          f"{sum(1 for p in places if p.place_type == 'rental_area')} rental areas.")
    return places
