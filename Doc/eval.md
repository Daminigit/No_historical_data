# Evaluation Guide: Location List Builder

**What this file is for:** A human evaluator or CI runner uses this document to judge whether the tool is correct, safe, and production-ready. Each section maps to a specific failure mode that has caused real problems in location-targeting workflows.

---

## 1. Automated Test Suite

Run first. If any test fails, stop — do not proceed to manual checks.

```bash
pytest tests/ -v
```

### Required tests and what they catch

| Test file | What it validates | Pass condition |
|---|---|---|
| `tests/test_emi.py` | EMI formula correctness | ₹96 L unit, 20% down, 8.5% pa, 20 yr → EMI in range ₹66,500–₹67,500 |
| `tests/test_score.py` | Scoring bands and drive-time decay | ratio 0.53 → High; ratio 0.20 → dropped; IT park at 10 min > IT park at 40 min |
| `tests/test_geocode.py` | Coordinate validation logic | Out-of-radius point → dropped; city-bbox → dropped; valid point → 4 d.p. coords |
| `tests/test_output_format.py` | Output line format | Every line matches `^\(\d+km:-?\d+\.\d{4}:-?\d+\.\d{4}\)$`; no spaces |
| `tests/test_no_latlng.py` | Ambiguous address abort | Clear error message printed; no output files written; exit code ≠ 0 |
| `tests/test_golden.py` | End-to-end with mocked APIs | Output matches `tests/fixtures/expected_locations.txt` exactly |

> [!IMPORTANT]
> All six test files must pass with **zero failures** before any manual check is performed.

---

## 2. EMI Calculation Check

**Why it matters:** An incorrect EMI means the rent/EMI ratio is wrong, which silently targets the wrong neighbourhoods.

### Procedure

1. Pick any `available` unit from the project JSON. Note `price_min_inr`.
2. Apply the formula by hand:

   ```
   loan = price_min_inr × (1 − down_payment_pct / 100)
   r    = (interest_rate_pct / 100) / 12
   n    = tenure_years × 12
   EMI  = loan × r × (1 + r)^n / ((1 + r)^n − 1)
   ```

3. Open `output/locations_report.csv`. Find a rental area row for that unit type.
4. Compare the `emi` column value to your hand calculation.

### Pass condition

Difference ≤ ₹100 (rounding only). Any larger difference = **FAIL**.

### Reference value (Aurelia Heights)

| Unit | Price | Down | Loan | EMI (expected) |
|---|---|---|---|---|
| 2 BHK | ₹96,00,000 | 20% | ₹76,80,000 | ~₹67,000/mo |

---

## 3. Coordinate Source Audit

**Why it matters:** The tool's core rule is that no coordinate may come from the LLM. A violation puts circles in wrong locations.

### Procedure

1. Enable verbose logging: `python build_locations.py --project <file> --verbose`
2. For every place in `output/locations_report.csv` where `kept = yes`:
   - Confirm `lat` and `lng` columns are populated
   - Cross-reference each coordinate against the cached geocoding response in `cache/geocode/`
3. Confirm the LLM cache entry (`cache/llm/`) contains **no numeric lat/lng fields** in the raw response

### Pass conditions

- [ ] Every kept place's coordinates match its geocoding cache entry exactly
- [ ] No `lat`/`lng` key appears in any `cache/llm/*.json` response that was used to populate a `Place` object
- [ ] All coordinates have exactly **4 decimal places** in the output file

---

## 4. Rent Source Audit

**Why it matters:** A rent without a verified source is inadmissible. Targeting decisions based on stale or fabricated rents are a compliance risk.

### Procedure

Open `output/locations_report.csv`. For every row where `type = rental_area` and `kept = yes`:

| Column | Check |
|---|---|
| `rent_2bhk` or `rent_3bhk` | Non-zero, plausible for the city (₹10,000–₹1,50,000) |
| `rent_source` | A valid URL (starts with `http`); not empty |
| `rent_date` | A date string or "current"; not empty |

### Pass conditions

- [ ] Zero rental area rows where `rent_source` is blank or `null`
- [ ] At least one of `rent_2bhk`, `rent_3bhk` is non-zero for every kept rental area
- [ ] Sample 3 source URLs — open them and confirm the rent figure on that page is plausible

> [!WARNING]
> If any kept rental area has a missing source URL, the entire run **fails** this check. Do not approve the output for campaign use.

---

## 5. Scoring Integrity Check

**Why it matters:** Mis-scored places waste ad budget on the wrong audience.

### Procedure

Pick 3 rental areas from the report — one with a High score, one Medium, one dropped (Low).

For each, manually verify:

1. **Ratio check:** `ratio = rent / emi`. Compute by hand using values in the report.
2. **Band check:** Confirm the ratio falls in the band that matches the `score` column.
3. **Drive-time adjustment:** The High-scored area should have a shorter drive time than a Medium-scored area with a similar ratio.

| Band | Ratio range | Expected score label |
|---|---|---|
| Low | < 0.30 | dropped |
| Medium | 0.30–0.45 | medium |
| High | 0.45–0.90 | high |
| Medium | > 0.90 | medium |

### Pass conditions

- [ ] Hand-calculated ratio matches report `ratio` column (± 0.01)
- [ ] Score label matches the ratio band table
- [ ] No dropped place has a ratio ≥ 0.30 (these should have been kept)
- [ ] No High-scored place has a drive time > `max_drive_minutes`

---

## 6. Output Format Check

**Why it matters:** A single malformed line silently breaks Google Ads bulk import with no user-visible error.

### Procedure

```bash
# Check every line matches the required format
grep -vP '^\(\d+km:-?\d+\.\d{4}:-?\d+\.\d{4}\)$' output/google_ads_locations.txt
```

Expected output: nothing (zero non-matching lines).

Also check:

```bash
# No line exceeds 500 entries
wc -l output/google_ads_locations.txt

# No spaces in the file
grep ' ' output/google_ads_locations.txt
```

### Pass conditions

- [ ] `grep -vP` returns zero matches
- [ ] Line count ≤ 500
- [ ] `grep ' '` returns zero matches
- [ ] Radius values are integers (e.g. `3km`, `2km`) — no decimals

---

## 7. Google Ads Editor Import Test

**Why it matters:** The format check above only validates syntax. This validates semantic correctness — that the targets actually resolve to real places in Google's location database.

### Procedure

1. Open Google Ads Editor
2. Select any campaign
3. Go to **Keywords and Targeting → Locations → Make multiple changes**
4. Paste the full contents of `output/google_ads_locations.txt`
5. Click **Process**, then review

### Pass conditions

- [ ] Zero "unresolved location" warnings
- [ ] All circles appear on the map
- [ ] Circles are around IT parks and residential areas — **not** over water, forests, or empty land
- [ ] No circle is centred outside the city the project is in

---

## 8. Map Visual Inspection

**Why it matters:** Automated checks cannot verify that circles are placed on real, relevant places rather than technically-valid-but-wrong points.

### Procedure

1. After the Ads Editor import, switch to the **Map** view
2. Zoom to the project's city
3. Spot-check at least 5 circles — 3 IT parks, 2 rental areas

### Checklist

| Circle | Expected | Red flag |
|---|---|---|
| IT park circles | Centred on a tech park / office complex | Centred on a road, field, or residential block |
| Rental circles | Centred on a dense residential locality | Centred on an industrial zone or empty land |
| Radius sizes | IT parks = `radius_km_it_park` km; rental = `radius_km_rental` km | Any circle dramatically larger or smaller |
| Coverage | Distributed across the commute zone | All circles clustered in one small area |

---

## 9. Determinism Check (Cache Correctness)

**Why it matters:** A non-deterministic tool produces different outputs on each run, making it impossible to audit what targeting was active at campaign launch.

### Procedure

```bash
# Run once
python build_locations.py --project aurelia_heights_project_info.json
cp output/google_ads_locations.txt /tmp/run1.txt

# Run again (cache should be warm)
python build_locations.py --project aurelia_heights_project_info.json
cp output/google_ads_locations.txt /tmp/run2.txt

# Compare
diff /tmp/run1.txt /tmp/run2.txt
```

### Pass condition

`diff` produces **zero output** — files are byte-identical.

---

## 10. Second-City Portability Test

**Why it matters:** The problem statement requires the tool to work for any project without code changes. This is a hard requirement before production sign-off.

### Procedure

1. Obtain or create a project JSON for a project in a different Indian city (e.g. Pune, Hyderabad, Chennai)
2. Run the tool with no changes to code or `config.yaml` beyond the `--project` flag

   ```bash
   python build_locations.py --project <other_city_project>.json
   ```

3. Apply all checks from sections 3–8 to the new output

### Pass conditions

- [ ] Both output files produced with no errors or code changes
- [ ] Geocoded coordinates are in the correct city
- [ ] Drive times are plausible for that city's traffic
- [ ] Output lines pass the format check (section 6)

---

## 11. Security & Config Check

**Why it matters:** API keys in code or logs are a critical security incident.

### Checklist

- [ ] `grep -r "AIza" .` → zero results (Google API key pattern)
- [ ] `grep -r "sk-" .` → zero results (OpenAI key pattern)
- [ ] `.env` is in `.gitignore` and not committed (`git status` shows it as untracked or ignored)
- [ ] `cache/` is in `.gitignore`
- [ ] No API key appears in any log line printed to stdout during a run

---

## 12. Eval Scorecard

Use this to record the result of each check before approving a run for campaign use.

| # | Check | Result | Notes |
|---|---|---|---|
| 1 | Automated test suite | ☐ Pass / ☐ Fail | |
| 2 | EMI calculation | ☐ Pass / ☐ Fail | |
| 3 | Coordinate source audit | ☐ Pass / ☐ Fail | |
| 4 | Rent source audit | ☐ Pass / ☐ Fail | |
| 5 | Scoring integrity | ☐ Pass / ☐ Fail | |
| 6 | Output format | ☐ Pass / ☐ Fail | |
| 7 | Google Ads Editor import | ☐ Pass / ☐ Fail | |
| 8 | Map visual inspection | ☐ Pass / ☐ Fail | |
| 9 | Determinism (cache) | ☐ Pass / ☐ Fail | |
| 10 | Second-city portability | ☐ Pass / ☐ Fail | |
| 11 | Security & config | ☐ Pass / ☐ Fail | |

**Sign-off:** All 11 checks must be **Pass** before the output is used in a live campaign.

> [!CAUTION]
> Do not paste `google_ads_locations.txt` into a live campaign until checks 4 (rent sources), 7 (Ads Editor import), and 8 (map visual inspection) are manually confirmed. Automated tests alone are not sufficient for campaign approval.
