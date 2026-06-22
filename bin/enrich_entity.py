#!/usr/bin/env python3
"""
Enrich an entity using Nominatim (search + details), Overpass (optional) and websearch fallback.

Behavior:
 - If `entities/<slug>.md` exists, it is read and frontmatter updated in-place (unless --out is given)
 - If entity doesn't exist, a minimal scaffold is created unless --dry-run

Example:
  python3 bin/enrich_entity.py --slug tai_po --nominatim-limit 3 --out entities/tai_po.md
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import json
import yaml
from typing import Any, Dict, List, Optional

from bin.search_nominatim import search
from bin.fetch_nominatim import fetch_details

ENT_DIR = Path("entities")


def read_frontmatter(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}
    y = m.group(1)
    return yaml.safe_load(y) or {}


def write_frontmatter(path: Path, fm: Dict[str, Any], body: Optional[str] = None):
    ENT_DIR.mkdir(parents=True, exist_ok=True)
    if body is None:
        if path.exists():
            text = path.read_text(encoding="utf8")
            m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
            body = m.group(2) if m else ""
        else:
            body = f"# {fm.get('names', {}).get('en', '')}\n\nShort description.\n"
    yaml_text = yaml.safe_dump(fm, allow_unicode=True)
    out = f"---\n{yaml_text}---\n\n{body}"
    path.write_text(out, encoding="utf8")


def nominatim_type_to_code(t: str) -> str:
    # geopy returns osm_type like 'node', 'way', 'relation'
    t = t.lower()
    return {"node": "N", "way": "W", "relation": "R"}.get(t, "N")


def best_candidate_from_search(results: List[Dict[str, Any]]):
    if not results:
        return None
    # Prefer exact match on display_name or namedetails, otherwise return first
    return results[0]


def enrich_entity(
    slug: str,
    name: Optional[str] = None,
    limit: int = 3,
    fetch_geom: bool = True,
    source_version: Optional[str] = None,
) -> Dict[str, Any]:
    ent_file = ENT_DIR / f"{slug}.md"
    fm = read_frontmatter(ent_file)
    if not fm:
        # create minimal frontmatter
        fm = {
            "id": slug,
            "names": {"en": name or slug, "zh": ""},
            "category": "poi",
            "lat": None,
            "lon": None,
            "source": "gov_hk/ALS-GeoJSON",
            "last_updated": None,
        }
    # choose search name
    search_name = None
    if name:
        search_name = name
    else:
        search_name = fm.get("names", {}).get("en") or slug

    results = search(search_name, limit=limit, polygon_geojson=True)
    if not results:
        return {"status": "no_candidates", "slug": slug}

    candidate = best_candidate_from_search(results)

    # Save some nominatim metadata
    nominatim_meta = {
        "display_name": candidate.get("display_name"),
        "osm_type": candidate.get("osm_type"),
        "osm_id": candidate.get("osm_id"),
    }

    if fetch_geom and candidate.get("osm_type") and candidate.get("osm_id"):
        # fetch details
        osmtype_code = nominatim_type_to_code(candidate["osm_type"])  # N/W/R
        osmid = int(candidate["osm_id"]) if candidate.get("osm_id") else None
        if osmid:
            details = fetch_details(
                osmtype_code, osmid, c=candidate.get("class"), addressdetails=1
            )
            # geometry_ref is a pointer to the nominatim detail
            fm.setdefault("geometry_ref", f"nominatim://{osmtype_code}/{osmid}")
            # add address-based assigned_district if available
            address = details.get("address", {})
            # Some Nominatim responses may contain address as a list; prefer the first dict
            if isinstance(address, list):
                address = address[0] if address and isinstance(address[0], dict) else {}
            # prefer named city/suburb/suburb or city fields
            district = (
                address.get("suburb")
                or address.get("city")
                or address.get("county")
                or address.get("village")
                or address.get("municipality")
                or None
            )
            if district:
                fm["assigned_district"] = district
            # also add bounding conflict: if polygon provided add to tags
            if details.get("geojson"):
                fm.setdefault("tags", [])
                fm["tags"].append("nominatim-polygon")

    # add nominatim metadata to tags
    if not fm.get("tags"):
        fm["tags"] = []
    fm["tags"].append("nominatim")

    # set source version if provided
    if source_version:
        fm["source_version"] = source_version

    # persist last_updated
    fm["last_updated"] = __import__("datetime").date.today().isoformat()

    # write out
    write_frontmatter(ent_file, fm)

    return {
        "status": "ok",
        "slug": slug,
        "nominatim": nominatim_meta,
        "frontmatter": fm,
    }


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", help="Entity slug (filename)")
    parser.add_argument("--name", help="Name to search for (if different from slug)")
    parser.add_argument("--nominatim-limit", type=int, default=3)
    parser.add_argument(
        "--no-geom",
        dest="fetch_geom",
        action="store_false",
        help="Don't fetch full nominatim details/polygon",
    )
    parser.add_argument("--source-version", default=None)
    args = parser.parse_args(argv)

    if not args.slug:
        parser.print_usage()
        return 2

    r = enrich_entity(
        args.slug,
        args.name,
        limit=args.nominatim_limit,
        fetch_geom=args.fetch_geom,
        source_version=args.source_version,
    )
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
