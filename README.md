# Location List Builder (Google Ads Radius Targeter)

A production-ready pipeline that takes a real estate project info JSON, discovers high-value employment hubs (IT parks) and affluent residential rental localities within peak commute distance, scores them based on travel time and rent-to-EMI affordability, and exports ready-to-paste Google Ads radius targeting coordinates and search keywords.

---

## Architecture Overview

The pipeline executes a deterministic 6-step workflow orchestrated by `build_locations.py`:

```
[Project Info JSON]
         │
         ▼
Step 1: Read Project (`steps/read_project.py`)
   ├── Validates project name, location (lat/lng or geocodes address).
   └── Computes monthly loan EMI for each available unit (2BHK, 3BHK).
         │
         ▼
Step 2: Place & Keyword Discovery (`steps/list_places.py`)
   ├── Queries configured LLM (Groq or Gemini) for IT parks & residential rental localities + rents.
   ├── Extracts 3–5 trending Google search keywords per location.
   └── Anti-hallucination guard: strips any LLM coordinates/distances.
         │
         ▼
Step 3: Geocoding Validation (`steps/geocode.py`)
   ├── Google Geocoding API verifies exact lat/lng for every place.
   └── Rejects vague city-level matches (whole-city bbox) or places beyond search radius, while accepting verified residential neighborhoods.
         │
         ▼
Step 4: Commute Analysis (`steps/drive_times.py`)
   ├── Google Distance Matrix API fetches peak morning commute time (Next weekday 8:30 AM IST).
   └── Drops locations exceeding `max_drive_minutes` (e.g. > 60 min).
         │
         ▼
Step 5: Scoring (`steps/score.py`)
   ├── IT Parks: Proximity decay score (shorter commute = higher score).
   └── Rental Areas: Rent ÷ EMI affordability ratio (drops low-rent areas whose tenants cannot afford this project).
         │
         ▼
Step 6: Output Generation (`steps/write_output.py`)
   ├── Deduplicates overlapping circles within `overlap_threshold_km`.
   ├── Caps targets at `max_targets`.
   └── Writes Google Ads targeting file, audit CSV, and keyword mapping CSV.
```

---

## Output Files

All results are written to `output/`:

1. **`output/google_ads_locations.txt`**:
   * Strict format: `(radius km:latitude:longitude)` with 4 decimal places (e.g., `(3km:12.9858:77.7356)`).
   * **Ready for bulk paste into Google Ads Editor** under *Keywords and Targeting → Locations → Make multiple changes*.
2. **`output/campaign_a_local_radius.txt`**:
   * **Campaign A: Local Radius**
   * **Setting:** `Presence` ("People in or regularly in your targeted locations").
   * **Locations:** Targeted non-overlapping circles (IT parks & rental areas).
   * **Keywords:** Generic real estate keywords (`2 BHK flats`, `new apartments`, `ready to move flats`). Generic terms work here without wasted spend because physical location is strictly filtered.
   * **Negative Keywords:** Shared negative list.
3. **`output/campaign_b_rest_of_geo.txt`**:
   * **Campaign B: Rest of Bengaluru / India**
   * **Setting:** `Presence or interest` ("People in, regularly in, or who have shown interest in your targeted locations").
   * **Locations:** `Bengaluru` (or India), with **Campaign A's circles strictly EXCLUDED** so the two campaigns never compete with each other.
   * **Keywords:** Must include place names (`flats in Whitefield`, `Hoodi apartments`, `2 BHK near ITPL`).
   * **Two Cautions:**
     1. City-wide terms like *"flats in Bangalore"* are broad and expensive. Give higher budget/bids to specific terms and bid lower (-40% to -50% CPC) on city-wide ones.
     2. Apply the exact same negative keyword list to both campaigns.
4. **`output/negative_keywords.txt`**:
   * Shared negative keyword list (rent, PG, lease, resale, second hand, jobs, salary, etc.) ready to paste into Google Ads.
5. **`output/google_ads_editor_campaigns.csv`**:
   * Full bulk-import CSV containing both Campaign A and Campaign B structures ready for 1-click import into Google Ads Editor.
6. **`output/locations_report.csv`**:
   * Complete audit trail with columns: `name`, `type`, `lat`, `lng`, `drive_minutes`, `rent_2bhk`, `rent_3bhk`, `rent_source`, `rent_date`, `emi`, `ratio`, `score`, `score_label`, `score_reason`, `kept`, `drop_reason`, `trending_keywords`.
7. **`output/location_keywords.csv`**:
   * Maps each kept target to high-intent Google search keywords.

---

## Setup & Quickstart

### Prerequisites
* Python >= 3.10
* Google Maps API Key (with **Geocoding API** and **Distance Matrix API** enabled)
* An LLM provider API Key: **Groq** (`GROQ_API_KEY`) or **Google Gemini** (`GEMINI_API_KEY`)

### 1. Installation
```bash
# Clone the repository and navigate into it
cd No_historical_data

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Optional: if using Gemini as LLM provider
pip install google-generativeai
```

### 2. Environment Variables
Copy `.env.example` to `.env` and fill in your API keys:
```bash
cp .env.example .env
```
Edit `.env`:
```env
# Google Maps API key (Geocoding API + Distance Matrix API enabled)
GOOGLE_MAPS_API_KEY=AIzaSy...

# LLM Provider: "groq" (default) or "gemini"
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...

# If using Gemini instead of Groq:
# LLM_PROVIDER=gemini
# GEMINI_API_KEY=AIzaSy...
```

### 3. Running the Pipeline
Run on any project JSON file:
```bash
python build_locations.py --project aurelia_heights_project_info.json
```

---

## Project Info JSON Format

The pipeline is completely generic and works with any project in any city. It supports standard or flat JSON:

```json
{
  "project": {
    "name": "Aurelia Heights"
  },
  "location": {
    "lat": 12.9800,
    "lng": 77.7200,
    "address": "Hoodi, Whitefield",
    "city": "Bengaluru"
  },
  "units": [
    {
      "type": "2BHK",
      "status": "available",
      "price_min_inr": 9600000
    },
    {
      "type": "3BHK",
      "status": "available",
      "price_min_inr": 13500000
    }
  ]
}
```
*(If `lat` and `lng` are omitted, Google Geocoding will resolve the address automatically).*

---

## Configuration (`config.yaml`)

Tunable parameters:
* `search_radius_km`: Discovery boundary around project (e.g., `25` km).
* `max_drive_minutes`: Peak commute cutoff (e.g., `60` min).
* `radius_km_it_park`: Targeting radius circle for IT parks (e.g., `5` km).
* `radius_km_rental`: Targeting radius circle for rental localities (e.g., `3` km).
* `max_targets`: Max number of targets to export (hard cap 500).
* `down_payment_pct`, `interest_rate_pct`, `tenure_years`: Home loan EMI assumptions.
* `ratio_bands`: Rent ÷ EMI ratio thresholds.

---

## Caching

All remote API calls (LLM discovery, Geocoding, Distance Matrix) are cached via SHA-256 in `cache/`. Re-running the pipeline on the same project is instant, zero-cost, and deterministic.

---

## Testing

Run the test suite with `pytest`:
```bash
pytest
```
All unit tests cover EMI calculations, boundary checks, ambiguity aborts, deduplication, regex compliance, and output format.
