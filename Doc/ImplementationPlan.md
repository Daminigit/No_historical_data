# Implementation Plan: Location List Builder

**Roadmap tasks:** 1.2–1.4 | **Entry point:** `build_locations.py`

---

## Overview

Six phases, each independently testable. Complete them in order — every phase depends on the one before it. The tool is "done" when all acceptance criteria in the Problem Statement are met.

```
Phase 0 → Scaffold
Phase 1 → Read project (Step 1)
Phase 2 → Discover places (Step 2)
Phase 3 → Geocode + drive times (Steps 3 & 4)
Phase 4 → Score + write output (Steps 5 & 6)
Phase 5 → Tests & validation
```

---

## Phase 0 — Project Scaffold

**Goal:** Runnable skeleton with no business logic yet.

### Tasks

- [ ] **0.1** Create repo structure

  ```
  build_locations.py
  config.yaml
  models.py
  steps/__init__.py
  steps/read_project.py
  steps/list_places.py
  steps/geocode.py
  steps/drive_times.py
  steps/score.py
  steps/write_output.py
  cache/.gitkeep
  output/.gitkeep
  tests/fixtures/
  .env.example
  .gitignore          # cache/, output/, .env, __pycache__
  ```

- [ ] **0.2** `pyproject.toml` / `requirements.txt` — declare dependencies

  | Package | Purpose |
  |---|---|
  | `requests` | Google API calls |
  | `pyyaml` | Parse `config.yaml` |
  | `python-dotenv` | Load `.env` |
  | `openai` or `google-generativeai` | LLM client |
  | `pytest` | Tests |

- [ ] **0.3** `models.py` — define dataclasses

  ```python
  @dataclass
  class UnitEMI:
      unit_type: str       # e.g. "2BHK"
      price_min_inr: float
      emi_monthly: float

  @dataclass
  class Place:
      name: str
      place_type: str      # "it_park" | "rental_area"
      lat: float | None = None
      lng: float | None = None
      drive_minutes: float | None = None
      rent_2bhk: float | None = None
      rent_3bhk: float | None = None
      rent_source: str | None = None
      rent_date: str | None = None
      emi: float | None = None
      ratio: float | None = None
      score: float | None = None
      score_reason: str | None = None
      kept: bool = True
      drop_reason: str | None = None

  @dataclass
  class ProjectData:
      name: str
      lat: float
      lng: float
      city: str
      unit_emis: list[UnitEMI]
  ```

- [ ] **0.4** `config.yaml` — default settings

  ```yaml
  search_radius_km: 15
  max_drive_minutes: 45
  radius_km_it_park: 3
  radius_km_rental: 2
  max_targets: 50
  overlap_threshold_km: 1.0
  down_payment_pct: 20
  interest_rate_pct: 8.5
  tenure_years: 20
  ratio_bands:
    - max: 0.30
      score: 1
      label: low
    - max: 0.45
      score: 5
      label: medium
    - max: 0.90
      score: 10
      label: high
    - max: 999
      score: 5
      label: medium
  ```

- [ ] **0.5** `build_locations.py` — stub orchestrator with argparse

  ```python
  python build_locations.py --project <path>
  ```

- [ ] **0.6** `cache/` utility — `cache.py` with `get(key)` / `set(key, data)` using SHA-256 keyed JSON files

**Phase 0 done when:** `python build_locations.py --project any.json` runs without crashing (even if it does nothing yet).

---

## Phase 1 — Read the Project (Step 1)

**Goal:** Parse the project JSON, resolve coordinates if missing, compute unit EMIs.

### Tasks

- [ ] **1.1** Implement `steps/read_project.py`

  - Load and validate the JSON (required fields: `project.name`, `location`, `units`)
  - If `location.lat` and `location.lng` are present → use them directly
  - If absent → call Google Geocoding API with `location.address + ", " + location.city`
  - **Abort condition:** if the Geocoding result has a `geometry.location_type` of `APPROXIMATE` or the bounding box spans > 5 km → exit with:
    ```
    Error: address resolves to a city/region, not a precise point.
    Please add lat/lng to the project JSON.
    ```
  - Extract `units[]` where `status == "available"` and `price_min_inr` is set
  - Compute EMI for each unit type:

    ```
    loan = price_min_inr × (1 − down_payment_pct / 100)
    r    = (interest_rate_pct / 100) / 12
    n    = tenure_years × 12
    EMI  = loan × r × (1 + r)^n / ((1 + r)^n − 1)
    ```

  - Return a `ProjectData` instance

- [ ] **1.2** Wire Step 1 into `build_locations.py`

- [ ] **1.3** Manual test: run with Aurelia Heights JSON, confirm correct coords and EMI values appear in logs

**Phase 1 done when:** EMI printed for each available unit type matches a hand calculation.

---

## Phase 2 — Discover Places (Step 2)

**Goal:** Use the LLM to find IT parks and rental areas with rents and sources.

### Tasks

- [ ] **2.1** Implement `steps/list_places.py`

  - Build the LLM prompt (see template below)
  - Call LLM with web-search tool enabled
  - Parse the structured response into `List[Place]`
  - **Validation:** reject any place that arrives with coordinates or drive times; log a warning and strip them
  - Cache the response under `cache/llm/<sha256(prompt)>.json`

- [ ] **2.2** LLM prompt template

  ```
  You are a real estate market researcher.

  Project address: {address}, {city}
  Search radius: {search_radius_km} km

  Task 1 — IT parks
  List every IT park, tech park, and large office campus within {search_radius_km} km of the project address.
  For each, return: name only. Do NOT include coordinates or distances.

  Task 2 — Rental areas
  List residential localities within {search_radius_km} km.
  For each, return:
  - name
  - typical monthly rent for a 2 BHK (₹)
  - typical monthly rent for a 3 BHK (₹)
  - the URL of the page you got the rent from
  - the date of that page (or "current" if it's live data)
  Do NOT include coordinates or distances.

  Return JSON only, with this structure:
  {
    "it_parks": [{"name": "..."}],
    "rental_areas": [{"name": "...", "rent_2bhk": 0, "rent_3bhk": 0, "source_url": "...", "source_date": "..."}]
  }
  ```

- [ ] **2.3** Wire Step 2 into orchestrator

- [ ] **2.4** Manual test: run with Aurelia Heights JSON, inspect raw LLM output and parsed places

> [!IMPORTANT]
> Any place with coordinates supplied by the LLM must be silently stripped. Coordinates must only come from Phase 3.

**Phase 2 done when:** Parsed lists of IT parks and rental areas print to stdout; each rental area has a non-empty `source_url`.

---

## Phase 3 — Geocode & Drive Times (Steps 3 & 4)

**Goal:** Attach real coordinates and peak-hour drive times to every candidate place.

### Tasks

- [ ] **3.1** Implement `steps/geocode.py`

  - For each place, query Google Geocoding API: `f"{place.name}, {city}"`
  - Cache under `cache/geocode/<sha256(query)>.json`
  - Acceptance checks per result:
    - `location_type` must not be `APPROXIMATE`
    - Resolved point must be within `search_radius_km` of the project point (Haversine)
    - Bounding box diagonal must be < 5 km (filters out whole-city matches)
  - On failure: set `place.kept = False`, `place.drop_reason = "geocode failed: <reason>"`
  - Round coordinates to 4 decimal places

- [ ] **3.2** Implement `steps/drive_times.py`

  - Batch all geocoded places into a single Distance Matrix API call (max 25 destinations per call; chunk if needed)
  - Departure time: next weekday at 08:30 local time (use `traffic_model=best_guess`)
  - Cache under `cache/distance/<sha256(payload)>.json`
  - Attach `drive_minutes` to each place
  - Drop places where `drive_minutes > max_drive_minutes`

- [ ] **3.3** Wire Steps 3 & 4 into orchestrator

- [ ] **3.4** Manual test: print geocoded coords and drive times for Aurelia Heights run; spot-check 3–5 places in Google Maps

**Phase 3 done when:** Every kept place has a lat/lng (4 d.p.) and a drive time; no coordinate value came from the LLM.

---

## Phase 4 — Score & Write Output (Steps 5 & 6)

**Goal:** Score every kept place, deduplicate overlapping circles, and write both output files.

### Tasks

- [ ] **4.1** Implement `steps/score.py`

  - **IT parks** — score formula:

    ```
    score = max(1, 10 − (drive_minutes / max_drive_minutes) × 9)
    ```

  - **Rental areas:**
    1. For each `UnitEMI` in `project.unit_emis`, find the matching rent field (`rent_2bhk` for `2BHK`, etc.)
    2. Compute `ratio = rent / emi`
    3. Look up the ratio in `config.ratio_bands` to get a base score
    4. Drive-time adjustment: multiply by `(1 − 0.3 × drive_minutes / max_drive_minutes)`
    5. Take the best score across all unit types
  - Drop rental areas where the base score is `low` (ratio < 0.30)
  - Set `.score`, `.score_reason` on each place

- [ ] **4.2** Implement `steps/write_output.py`

  - Sort kept places by score descending
  - Deduplication: for each pair of same-type places within `overlap_threshold_km` of each other (Haversine), drop the lower-scored one
  - Apply `max_targets` cap (hard cap at 500 regardless)
  - Write `output/google_ads_locations.txt`:

    ```python
    radius = config.radius_km_it_park if place.place_type == "it_park" else config.radius_km_rental
    line = f"({radius}km:{place.lat:.4f}:{place.lng:.4f})"
    ```

  - Write `output/locations_report.csv` — all places, kept and dropped, with all fields

- [ ] **4.3** Wire Steps 5 & 6 into orchestrator; create `output/` if missing

- [ ] **4.4** Manual test with Aurelia Heights:
  - Open `locations_report.csv` — verify rent, source, EMI, ratio, score columns are all populated
  - Cross-check one EMI value by hand
  - Paste `google_ads_locations.txt` into Google Ads Editor → confirm no unresolved locations

**Phase 4 done when:** Both output files exist, are valid, and paste cleanly into Google Ads Editor.

---

## Phase 5 — Tests & Validation

**Goal:** Automated test coverage for core logic; end-to-end run on a second city.

### Tasks

- [ ] **5.1** `tests/test_emi.py` — unit tests for the EMI formula

  - Known input (₹96 L, 20% down, 8.5%, 20 yr) → expect ~₹67,000/mo ± ₹500

- [ ] **5.2** `tests/test_score.py` — unit tests for scoring

  - Ratio 0.53 → High score
  - Ratio 0.20 → dropped (Low)
  - Ratio 1.10 → Medium score
  - IT park at 10 min → higher score than IT park at 40 min

- [ ] **5.3** `tests/test_geocode.py` — unit tests for coordinate validation

  - Point outside `search_radius_km` → dropped
  - Whole-city bounding box → dropped
  - Valid point → kept with 4 d.p. coordinates

- [ ] **5.4** `tests/test_output_format.py` — validate output line format

  - Each line matches regex `^\(\d+km:-?\d+\.\d{4}:-?\d+\.\d{4}\)$`
  - No spaces anywhere in the file

- [ ] **5.5** `tests/fixtures/` — golden-file test

  - `sample_project.json` — a real or synthetic second-city project JSON
  - `expected_locations.txt` — known expected output
  - Test: run pipeline with mocked API responses → compare output to expected file

- [ ] **5.6** End-to-end run on a second project in a different city (no code changes allowed)

  - Confirm both output files are produced with no errors
  - Spot-check circles on the Google Ads location map

- [ ] **5.7** `tests/test_no_latlng.py` — test abort on ambiguous address

  - Input JSON with no `lat`/`lng` and a city-only address → confirm clear error message, no output files written

**Phase 5 done when:** `pytest` passes with 0 failures; second-city run succeeds; ambiguous-address run aborts cleanly.

---

## Acceptance Criteria (from Problem Statement)

| # | Criterion | Covered by |
|---|---|---|
| 1 | Aurelia Heights run produces both output files with no errors | Phase 4 manual test |
| 2 | Second-city project works with no code changes | Phase 5.6 |
| 3 | JSON with no lat/lng and only a city address stops with a clear message | Phase 1.1, Phase 5.7 |
| 4 | Each rental area shows rent, source, EMI, ratio, score; EMI matches hand calc | Phase 4.4 |
| 5 | No coordinate or drive time in outputs came from the LLM | Phase 2.1 validation, Phase 3 |
| 6 | All tests in `tests/` pass | Phase 5 |
| 7 | Lines paste into Google Ads Editor with no unresolved locations | Phase 4.4 |
| 8 | Circles look right on Google Ads location map | Phase 4.4, Phase 5.6 |

---

## Dependencies & Risks

| Risk | Mitigation |
|---|---|
| LLM returns hallucinated rents with no source URL | Validation in Step 2: reject any rent entry missing `source_url`; log and drop |
| Geocoding API returns a whole-city result | Bounding-box size check in Step 3 (< 5 km diagonal) |
| Distance Matrix quota (100 elements/request free tier) | Chunk destinations into batches of 25; cache aggressively |
| LLM sneaks in coordinates | Strip any numeric field that looks like lat/lng from LLM response before creating `Place` objects |
| Two projects cached to the same key | Cache key includes project name + address to avoid collisions |

---

## Environment Setup

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Copy and fill in API keys
cp .env.example .env
# Add: GOOGLE_MAPS_API_KEY=...
#      LLM_API_KEY=...

# 3. Run
python build_locations.py --project aurelia_heights_project_info.json

# 4. Test
pytest tests/
```
