"""
build_locations.py — Entry point for the Location List Builder.

Usage:
    python build_locations.py --project <path-to-project-info.json>

Runs the 6-step pipeline:
  1. Read & validate project JSON, compute unit EMIs
  2. Discover IT parks & rental areas via LLM + Google Search
  3. Geocode each place (Google Geocoding API)
  4. Fetch peak-hour drive times (Google Distance Matrix API)
  5. Score each place (drive time + rent/EMI ratio)
  6. Deduplicate, cap, write output files

All remote calls are cached in cache/ — reruns on the same project are free and deterministic.
API keys are read from environment variables (see .env.example).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import yaml

# Load .env before any step imports that read env vars
load_dotenv()


def _load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    if not config_path.exists():
        sys.exit("Error: config.yaml not found. It should be in the same directory as build_locations.py.")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build Google Ads radius targets from a project info JSON."
    )
    parser.add_argument(
        "--project", required=True,
        help="Path to the project info JSON file (e.g. aurelia_heights_project_info.json)"
    )
    args = parser.parse_args()

    project_path = args.project
    if not Path(project_path).exists():
        sys.exit(f"Error: Project file not found: {project_path}")

    cfg = _load_config()

    print("=" * 60)
    print("Location List Builder")
    print("=" * 60)

    # Step 1 — Read project
    from steps.read_project import read_project
    project = read_project(project_path, cfg)
    print(f"\nProject : {project.name}")
    print(f"Location: {project.lat}, {project.lng} ({project.city})")
    print(f"Units   : {[f'{u.unit_type} EMI ₹{u.emi_monthly:,.0f}' for u in project.unit_emis]}")
    print()

    # Step 2 — Discover places
    from steps.list_places import list_places
    places = list_places(project, cfg)
    print()

    # Step 3 — Geocode
    from steps.geocode import geocode_places
    places = geocode_places(places, project, cfg)
    print()

    # Step 4 — Drive times
    from steps.drive_times import fetch_drive_times
    places = fetch_drive_times(places, project, cfg)
    print()

    # Step 5 — Score
    from steps.score import score_places
    places = score_places(places, project, cfg)
    print()

    # Step 6 — Write output
    from steps.write_output import write_outputs
    write_outputs(places, project, cfg)


if __name__ == "__main__":
    main()
