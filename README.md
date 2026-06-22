# HK Addresses Knowledge DB

This repository builds a canonical knowledge base of Hong Kong addresses, estates, streets, transport and other POIs for RAG and LLM training. It uses the gov.hk ALS GeoJSON dataset as the initial discovery source and OpenStreetMap/Nominatim for enrichment.

Key design decisions
- Single canonical knowledge repository in Git: each entity is a Markdown file under `entities/` with YAML frontmatter storing metadata and links (graph edges).
- Bulk geodata sources (ALS-GeoJSON from gov.hk and OSM via Overpass) are downloaded and inspected rather than performing heavy per-address reverse geocoding.
- Agents coordinate through GitHub issues; issues follow templates in `.github/ISSUE_TEMPLATE/`.

Documentation
 - [`docs/data-dictionary.md`](docs/data-dictionary.md) — field-by-field schema of the canonical dataset (`data/als_canonical_fixed.csv`), provenance, CRS, and licensing.

Contents
 - `bin/` — helper scripts (formerly `scripts/`) — repo moved to a `bin/` folder for executable utilities
  - `download_geojson.py` — download ALS GeoJSON and inspect schema (use `bin/download_geojson.py`)
  - `export_places_os.py` — export OSM place features for HK areas using Overpass (use `bin/export_places_os.py`)
  - `entity_create.py` — scaffold a new `entities/*.md` file (use `bin/entity_create.py`)
  - `enrich_entity.py` — Nominatim/Overpass/websearch-based entity enrichment and geometry_ref addition (use `bin/enrich_entity.py`)
  - `geojson_to_canonical.py` — normalise ALS GeoJSON features into canonical tabular format (use `bin/geojson_to_canonical.py`)
  - `fix_district_names.py` — map administrative district names to common short names and add `sub_district` to canonical data (use `bin/fix_district_names.py`)
  - `suggest_entities.py` — scan ALS addresses to propose missing entities and generate issue text (use `bin/suggest_entities.py`)
- `data/` — downloaded datasets (ALS zip)

Installation & usage (quickstart)
1. Create a Python virtual env and install requirements:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Download ALS GeoJSON (examples included in `scripts`):

```bash
python3 bin/download_geojson.py --output data --unzip --inspect
```
