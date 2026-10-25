# Location list: problem statement

**Roadmap tasks:** 1.2–1.4 (IT parks, rental areas, merged list). **Consumers:** 1.4a (main code) and campaign creation (3.3a, 3.3b).

---

## Problem

For any residential project, the ad campaigns need to know where to show ads. Two kinds of places matter:

- **IT parks within commute distance.** People who work there want a home close to work.
- **Rental areas whose renters could afford this project.** People renting today are future buyers, and the rent they pay shows roughly what they can afford.

Finding these by hand for each new project is slow and inconsistent. This tool takes a project info JSON (the same file the ads and WhatsApp agent use), finds the IT parks and rental areas around the project, scores them, and writes one list of radius targets (`output/google_ads_locations.txt`) that can be pasted straight into Google Ads.

> Aurelia Heights (Whitefield–Hoodi, Bengaluru) is the first project it runs on, not the only one.

---

## Where this fits in the workflow

1. Project data is verified and stored (project info JSON).
2. **This tool:** project info JSON → IT parks + rental areas → scored → radius targets.
3. Keywords are researched separately (tasks 1.5, 1.6).
4. Locations + keywords form the targeting pack (task 1.7).
5. Campaigns use the radius targets (tasks 3.2a, 3.2b, 3.3a, 3.3b).

---

## How it runs

```bash
python build_locations.py --project aurelia_heights_project_info.json
```

---

## Step 1: Read the project

From the project info JSON, read:

| Field | Used for |
|---|---|
| `project.name` | File names, report |
| `location.lat`, `location.lng` | The project point |
| `location.address`, `location.city` | Fallback when lat/lng are empty: turned into a point with the Google Geocoding API |
| `units[]` with `status = available`: `type`, `price_min_inr` | EMI per unit type, for rental scoring |

> If lat/lng are empty and the address only resolves to a city or pincode, stop and ask for coordinates, because every distance depends on this point.

---

## Step 2: List candidate places (LLM with web search)

Ask an LLM with web search, for the project's address:

- IT parks, tech parks and large office campuses within `search_radius_km`.
- Residential localities within `search_radius_km`, each with the current typical monthly rent for a 2 BHK and a 3 BHK, and the page the rent came from.

> The LLM returns names, rents and sources only. It **never** supplies coordinates or drive times; those come from Google's APIs in the next steps.

---

## Step 3: Coordinates (Google Geocoding API)

Geocode each name from step 2 with the city added (e.g. "ITPL, Bengaluru"). Drop names that don't resolve, or resolve to a whole city instead of a place, and list them in the report.

---

## Step 4: Drive times (Google Distance Matrix API)

Drive time from each place to the project at a weekday peak hour. Drop places over `max_drive_minutes`.

---

## Step 5: Score

**IT parks:** shorter drive time scores higher.

**Rental areas:** compare the area's rent with the EMI of the matching unit type.

**EMI formula** for each available unit type, from its lowest price:

```
loan = price_min × (1 − down_payment_pct)
EMI  = loan × r × (1 + r)^n ÷ ((1 + r)^n − 1)
```

where `r = annual rate ÷ 12` and `n = tenure in months`

**Ratio** = area's rent for that unit type ÷ EMI for that unit type. Use the best ratio across available types.

**Score by ratio band** (defaults in `config.yaml`, to tune):

| Rent ÷ EMI | What it suggests | Score |
|---|---|---|
| Below 0.30 | Renters likely can't afford this project | Low (dropped below cut-off) |
| 0.30–0.45 | A stretch for some | Medium |
| 0.45–0.90 | Rent level fits this project's EMI | High |
| Above 0.90 | Renters may buy something pricier | Medium |

Adjust for drive time: closer areas score higher.

> **Example** with the default assumptions (20% down, 8.5% a year, 20 years): the Aurelia Heights 2 BHK from ₹96 L has an EMI of about ₹67,000 a month. An area where 2 BHKs rent for ₹35,000 has a ratio of about 0.53, so it scores **high**.

---

## Step 6: Cut off and write the output

Keep places above the cut-off, up to `max_targets`. Remove circles that almost fully overlap, keeping the higher score. Write the two output files, highest score first.

---

## Inputs

| Input | Required | Notes |
|---|---|---|
| Project info JSON | Yes | Needs a location (lat/lng or a precise address) and at least one available unit with a price |
| `config.yaml` | No | Defaults below; change per project or city |
| API keys | Yes | Google Maps (Geocoding, Distance Matrix) and the LLM, from environment variables |

**Default settings in `config.yaml`:**

| Setting | Default | Meaning |
|---|---|---|
| `search_radius_km` | 15 | How far out to look |
| `max_drive_minutes` | 45 | Drop places further than this at peak hour |
| `radius_km_it_park` | 3 | Targeting circle around an IT park |
| `radius_km_rental` | 2 | Targeting circle around a rental locality |
| `max_targets` | 50 | Upper limit on the number of targets |
| `down_payment_pct` | 20 | Assumed down payment |
| `interest_rate_pct` | 8.5 | Assumed home loan rate; update when rates change |
| `tenure_years` | 20 | Assumed loan tenure |
| `ratio_bands` | see table above | Rent ÷ EMI bands and their scores |

---

## Outputs

### `output/google_ads_locations.txt`

One radius target per line, in the format Google Ads Editor accepts for bulk location targets: `(radius km:latitude:longitude)`.

```
(3km:12.9800:77.7200)
(2km:12.9900:77.7100)
```

*(Coordinates above are placeholders, not real values.)*

**How to use:**
- **Google Ads Editor (bulk):** Keywords and Targeting → Locations → Make multiple changes → paste the lines → Process → Keep. Search campaigns take location targets at the campaign level; Demand Gen takes them at the ad group level.
- **Google Ads web interface:** radius targets are added one at a time (Locations → Advanced search → Radius), so use Editor for more than a few.
- **API (tasks 3.3a, 3.3b):** the campaign code reads the same lines and turns each into a radius (proximity) target.

### `output/locations_report.csv`

One row per place considered, kept or dropped: name, type, coordinates, drive time, rent (2 BHK, 3 BHK), rent source, EMI, ratio, score, kept or dropped, and why. This is what a person checks before the targets go live.

---

## Rules

- Works for any project info JSON; nothing in the code is specific to one city or project.
- Coordinates and drive times come only from Google's APIs, **never** from the LLM.
- Every rent has a source page and date in the report. A rent without a source is not used.
- Every output line matches `(<number>km:<lat>:<lng>)` exactly, with no spaces; radius at least 1 km; at most 500 lines.
- Coordinates have 4 decimal places and lie within `search_radius_km` of the project.
- API keys come from environment variables, never from the code or the repo.
- LLM and API results are cached in `cache/`, so a rerun on the same project gives the same output.
- Ads must not claim that the EMI is "close to your rent" or similar. EMI is usually well above rent, and any EMI figure in an ad needs its assumptions stated. This tool uses rent only to choose where to advertise.

---

## Done when

- [ ] Running on the Aurelia Heights JSON produces both output files with no errors.
- [ ] Running on a second project JSON in another city works with no code changes.
- [ ] A JSON with no lat/lng and only a city as address stops with a clear message.
- [ ] Each rental area in the report shows rent, source, EMI, ratio and score, and the EMI matches a hand calculation.
- [ ] No coordinate or drive time in the outputs came from the LLM.
- [ ] All tests in `tests/` pass, including a sample input with a known expected output.
- [ ] The lines paste into Google Ads Editor with no unresolved locations.
- [ ] The circles look right on the Google Ads location map: around IT parks and rental areas, not over empty land.

---

## Out of scope

- Scraping listing sites directly; rents come from the LLM's web search, with sources recorded.
- Rental listing counts (number of renters per area); can be added later as a size signal.
- Location bid adjustments by score; every place in the list is targeted equally.
- Projects outside India (the defaults assume Indian home loans and cities).
- Creating the campaigns; that happens in tasks 3.3a and 3.3b.
