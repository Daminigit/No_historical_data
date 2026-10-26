# Location List Builder (Google Ads Radius Targeter)

A production-ready pipeline for real estate performance marketing. It takes a real estate project info JSON, discovers high-value employment hubs (IT parks, SEZs, industrial belts) and affluent residential rental localities within peak commute distance, scores them based on travel time and rent-to-EMI affordability, and exports ready-to-paste Google Ads radius targeting coordinates and search keywords.

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
   ├── Focuses strictly on realistic commuter corridors and adjacent feeder micro-markets.
   ├── Extracts 3–5 trending Google search keywords per location.
   └── Anti-hallucination guard: strips any LLM coordinates/distances.
         │
         ▼
Step 3: Geocoding Validation (`steps/geocode.py`)
   ├── Google Geocoding API verifies exact lat/lng for every place.
   ├── Supports large corporate/IT campuses (allowing APPROXIMATE with bbox < 12 km).
   └── Rejects whole-city matches (bbox > 12 km) or places beyond search radius.
         │
         ▼
Step 4: Commute Analysis (`steps/drive_times.py`)
   ├── Google Distance Matrix API fetches peak morning commute time (Next weekday 8:30 AM IST).
   └── Drops locations exceeding `max_drive_minutes` (e.g. > 60 min).
         │
         ▼
Step 5: Scoring & Affordability (`steps/score.py`)
   ├── IT Parks: Proximity decay score (shorter commute = higher score).
   ├── Rental Areas: Rent ÷ EMI affordability ratio (drops low-rent areas whose tenants cannot afford this project).
   └── Locality Safeguard: Project's immediate neighborhood (< 3 min drive) is always retained as a core catchment.
         │
         ▼
Step 6: Output Generation (`steps/write_output.py`)
   ├── Deduplicates overlapping circles (prunes circles with > 90% area overlap, keeping higher score).
   ├── Caps targets at `max_targets`.
   ├── Isolates outputs into project folders (`output/<project_slug>/`).
   └── Writes single Google Ads input file, campaign configs, audit report, and Editor import CSV.
```

---

## Output Structure

All outputs are neatly organized into dedicated project folders under `output/`:

```
output/
├── campaign_map.html                   # Multi-project interactive Leaflet visual dashboard
├── index.html                          # Root entry point for web server
├── aurelia/                            # Aurelia Heights (Bengaluru)
│   ├── google_ads_input.txt            # ⭐ Single result file (Locations + Search Keywords)
│   ├── google_ads_input.csv            # Spreadsheet-ready version of inputs
│   ├── locations_report.csv            # Full audit report & scoring
│   ├── campaign_a_local_radius.txt     # Campaign A: Local radius (Presence)
│   ├── campaign_b_rest_of_geo.txt      # Campaign B: Rest of geo (Exclusions + geo keywords)
│   ├── google_ads_editor_campaigns.csv # 1-Click import for Google Ads Editor
│   ├── google_ads_locations.txt        # Raw radius coordinates list
│   ├── location_keywords.csv           # Keywords mapped per target
│   └── negative_keywords.txt           # Shared negative keywords list
├── kunjban/                            # Kunjban Society (Nashik)
└── vision_flora/                       # Vision Flora (Pune)
```

### Core Output Files per Project

1. **`google_ads_input.txt` (⭐ Single Result File)**:
   * Combines all **radius targets** `(radius km:lat:lng)` and **deduplicated search keywords** into a single clean file for direct input into Google Ads.
2. **`google_ads_input.csv`**:
   * CSV version formatted for spreadsheet review or bulk import.
3. **`campaign_a_local_radius.txt`**:
   * **Campaign A: Local Radius**
   * **Setting:** `Presence` ("People in or regularly in your targeted locations").
   * **Locations:** Targeted non-overlapping circles (IT parks & rental areas).
   * **Keywords:** Generic real estate keywords (`2 BHK flats`, `new apartments`, `ready to move flats`).
4. **`campaign_b_rest_of_geo.txt`**:
   * **Campaign B: Rest of City / India**
   * **Setting:** `Presence or interest` ("People in, regularly in, or who have shown interest in your targeted locations").
   * **Locations:** Target city/country, with **Campaign A's circles strictly EXCLUDED** to avoid self-competition.
   * **Keywords:** Locality-specific terms (`flats in Whitefield`, `apartments near Hinjewadi`).
   * **Cautions:** Budget allocation guidance and negative keyword safeguards.
5. **`google_ads_editor_campaigns.csv`**:
   * Full bulk-import CSV containing both Campaign A and Campaign B structures ready for 1-click import into Google Ads Editor.
6. **`locations_report.csv`**:
   * Complete audit trail with columns: `name`, `type`, `lat`, `lng`, `drive_minutes`, `rent_2bhk`, `rent_3bhk`, `rent_source`, `rent_date`, `emi`, `ratio`, `score`, `score_label`, `score_reason`, `kept`, `drop_reason`, `trending_keywords`.
7. **`negative_keywords.txt`**:
   * Shared negative keyword list (`rent`, `PG`, `lease`, `resale`, `second hand`, `broker`, `jobs`, `salary`, etc.).

---

## Interactive Visual Map Dashboard

An interactive dark-mode Leaflet web dashboard is available to inspect targeting circles, commute connector lines, and campaign setups across all projects:

```bash
# Start local server
python3 -m http.server 8000 --directory output
```

Open in your browser: **[http://localhost:8000/campaign_map.html](http://localhost:8000/campaign_map.html)**

* **Project Switcher:** Switch between **Vision Flora (Pune)**, **Aurelia Heights (Bengaluru)**, and **Kunjban Society (Nashik)**.
* **Mode Tabs:** Toggle between **Campaign A (Local Radius)**, **Campaign B (Geo Exclusions)**, and **Cautions & Negatives**.

---

## Setup & Quickstart

### Prerequisites
* Python >= 3.10
* Google Maps API Key (with **Geocoding API** and **Distance Matrix API** enabled)
* LLM API Key: **Groq** (`GROQ_API_KEY`) or **Google Gemini** (`GEMINI_API_KEY`)

### 1. Installation
```bash
# Clone the repository
git clone https://github.com/Daminigit/No_historical_data.git
cd No_historical_data

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### 2. Environment Variables
Copy `.env.example` to `.env` and fill in your API keys:
```bash
cp .env.example .env
```

```env
# Google Maps API key (Geocoding API + Distance Matrix API enabled)
GOOGLE_MAPS_API_KEY=AIzaSy...

# LLM Provider: "groq" (default) or "gemini"
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

### 3. Running the Pipeline
Run on any project JSON file:
```bash
# Example 1: Aurelia Heights (Bengaluru)
python build_locations.py --project aurelia_heights_project_info.json

# Example 2: Kunjban Society (Nashik)
python build_locations.py --project kunjban_nashik_project_info.json

# Example 3: Vision Flora (Pune)
python build_locations.py --project vision_flora_pune_info.json
```

---

## Project Info JSON Format

The pipeline is completely generic and works with any project in any city:

```json
{
  "project": {
    "name": "Vision Flora"
  },
  "location": {
    "lat": 18.5990,
    "lng": 73.7980,
    "address": "Vision Flora, Pimple Saudagar, Pimpri-Chinchwad, Pune, Maharashtra 411027",
    "city": "Pune"
  },
  "units": [
    {
      "type": "2BHK",
      "status": "available",
      "price_min_inr": 8500000
    },
    {
      "type": "3BHK",
      "status": "available",
      "price_min_inr": 12000000
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
* `radius_km_it_park`: Targeting radius circle for IT parks (`3` km).
* `radius_km_rental`: Targeting radius circle for rental localities (`2` km).
* `overlap_threshold_ratio`: Area overlap threshold for deduplication (`0.90` = 90% overlap removed).
* `max_targets`: Max number of targets to export (hard cap 500).
* `down_payment_pct`, `interest_rate_pct`, `tenure_years`: Home loan EMI assumptions (`20%`, `8.5%`, `20` years).
* `ratio_bands`: Rent ÷ EMI ratio thresholds.

---

## Testing

Run the test suite with `pytest`:
```bash
pytest
```
All **43 unit tests** verify:
* EMI calculations
* Geocode bounding box and distance validation
* LLM parsing and coordinate stripping
* Commute scoring and ratio band classifications
* 90% circle overlap deduplication math
* Google Ads format compliance
