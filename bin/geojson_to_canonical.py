#!/usr/bin/env python3
"""
Normalize ALS GeoJSON features into a canonical tabular dataset.

Usage:
  python bin/geojson_to_canonical.py --in data/*.geojson --out data/als_canonical.csv --format csv
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Literal
import datetime
import pandas as pd
from tqdm import tqdm
import unicodedata

DEFAULT_SOURCE = "gov_hk/ALS-GeoJSON"
DEFAULT_FORMAT = "csv"

region_map = {
    "HK": "Hong Kong Island",
    "KLN": "Kowloon",
    "NT": "New Territories",
}


def extract_text_from_address(
    parts: Dict[str, Any], lang: Literal["zh", "en"] = "zh"
) -> str:
    if not parts:
        return ""
    pieces: List[str] = []

    block = parts.get("ChiBlock") or parts.get("EngBlock")
    if isinstance(block, dict):
        block_no = block.get("BlockNo", "")
        if block.get("BlockDescriptor"):
            block_descriptor = block.get("BlockDescriptor", "")
            if block_descriptor == "BLK":
                block_descriptor = " Block"
            elif block_descriptor == "HSE":
                block_descriptor = "House"
            if re.match(r"^[a-zA-Z]+$", block_descriptor) is not None:
                block_no = f"{block_descriptor} {block_no}"
            else:
                block_no = f"{block_no}{block_descriptor}"  # Chinese style
        if block_no:
            pieces.append(block_no)

    if "BuildingName" in parts:
        pieces.append(parts["BuildingName"])

    estate = parts.get("ChiEstate") or parts.get("EngEstate")
    if isinstance(estate, dict):
        estate_name = estate.get("EstateName")
        estate_phase = estate.get("ChiPhase") or estate.get("EngPhase")
        if estate_name:
            pieces.append(estate_name)
        if estate_phase:
            estate_phase_name = estate_phase.get("PhaseName")
            if estate_phase_name:
                pieces.append(estate_phase_name)
    elif estate:
        pieces.append(str(estate))

    village = parts.get("ChiVillage") or parts.get("EngVillage")
    if isinstance(village, dict):
        village_name = village.get("VillageName")
        if village_name:
            pieces.append(village_name)
    elif village:
        pieces.append(str(village))

    street = parts.get("ChiStreet") or parts.get("EngStreet")

    if isinstance(street, dict):
        # include building number if present
        if street.get("BuildingNoFrom"):
            building_no = ""
            if street.get("BuildingNoTo"):
                building_no = (
                    f"{street.get('BuildingNoFrom')}-{street.get('BuildingNoTo')}"
                )
            else:
                building_no = str(street.get("BuildingNoFrom"))

            if lang == "zh":
                building_no += "號"

            if building_no:
                pieces.append(building_no)

        if street.get("StreetName"):
            pieces.append(street.get("StreetName"))

    district = parts.get("ChiDistrict") or parts.get("EngDistrict")
    if district:
        pieces.append(district)

    region = parts.get("Region")
    if region:
        pieces.append(region_map.get(region, region))

    if lang == "zh":
        # reverse for Chinese
        pieces = list(reversed(pieces))
        text = " ".join([p for p in pieces if p])
    else:
        text = ", ".join([p for p in pieces if p])

    return text


def text_normalize(s: Optional[str]) -> Optional[str]:
    """Simple text normalization: full-width to half-width, trim spaces."""
    if not s:
        return s
    s = s.strip()
    return unicodedata.normalize("NFKC", s)


def normalize_feature(
    feature: Dict[str, Any],
    source: str = DEFAULT_SOURCE,
    source_version: Optional[str] = None,
) -> Dict[str, Any]:
    props = feature.get("properties", {}) or {}
    geo = feature.get("geometry") or {}
    coords = geo.get("coordinates") if geo else None
    lon, lat = (None, None)
    # Coordinates may be a flat point [lon, lat] or nested (MultiPoint / arrays).
    if coords and isinstance(coords, list):
        # Point-like: first element is a number
        if len(coords) >= 2 and isinstance(coords[0], (int, float)):
            lon = coords[0]
            lat = coords[1]
        # Nested: e.g. MultiPoint -> [[lon, lat], ...] -> take the first point
        elif coords and isinstance(coords[0], (list, tuple)) and len(coords[0]) >= 2:
            inner = coords[0]
            if isinstance(inner[0], (int, float)):
                lon = inner[0]
                lat = inner[1]

    address_block = props.get("Address", {}).get("PremisesAddress", {})
    csu = (address_block.get("BuildingCsuInformation") or {}).get("CsuId")
    geoaddr = address_block.get("GeoAddress") or csu

    chi = address_block.get("ChiPremisesAddress", {})
    eng = address_block.get("EngPremisesAddress", {})

    address_chi = extract_text_from_address(chi, lang="zh")
    address_eng = extract_text_from_address(eng, lang="en")

    # Extract components explicitly (building / estate / village / street)
    def pick_building(parts: Dict[str, Any]):
        # BuildingName may appear at top-level in the parts
        if not parts:
            return None
        name = parts.get("BuildingName")
        if name:
            return name
        return None

    def pick_estate(parts: Dict[str, Any]):
        if not parts:
            return None
        estate = parts.get("ChiEstate") or parts.get("EngEstate")
        if isinstance(estate, dict):
            return estate.get("EstateName")
        return None

    def pick_phase(parts: Dict[str, Any]):
        if not parts:
            return None
        phase = parts.get("ChiPhase") or parts.get("EngPhase")
        if isinstance(phase, dict):
            return phase.get("PhaseName")
        return None

    def pick_block(parts: Dict[str, Any]):
        if not parts:
            return None
        block = parts.get("ChiBlock") or parts.get("EngBlock")
        if isinstance(block, dict):
            block_no = block.get("BlockNo", "")
            if block.get("BlockDescriptor"):
                block_descriptor = block.get("BlockDescriptor", "")
                # Fix common abbreviation
                if block_descriptor == "BLK":
                    block_descriptor = "Block"
                elif block_descriptor == "HSE":
                    block_descriptor = "House"
                if re.match(r"^[a-zA-Z]+$", block_descriptor) is not None:
                    block_no = f"{block_descriptor} {block_no}"
                else:
                    block_no = f"{block_no}{block_descriptor}"  # Chinese style
            return block_no
        return None

    def pick_village(parts: Dict[str, Any]):
        if not parts:
            return None
        village = parts.get("ChiVillage") or parts.get("EngVillage")
        if isinstance(village, dict):
            return village.get("VillageName")
        return village

    def pick_street(parts: Dict[str, Any]):
        if not parts:
            return None
        street = parts.get("ChiStreet") or parts.get("EngStreet")
        if isinstance(street, dict):
            # prefer StreetName first
            name = street.get("StreetName") or street.get("Street")
            if name:
                return name
            # sometimes there may be nested objects
            return None
        return street

    building_chi = pick_building(chi)
    estate_chi = pick_estate(chi)
    phase_chi = pick_phase(chi)
    block_chi = pick_block(chi)
    village_chi = pick_village(chi)
    street_chi = pick_street(chi)
    building_eng = pick_building(eng)
    estate_eng = pick_estate(eng)
    phase_eng = pick_phase(eng)
    block_eng = pick_block(eng)
    village_eng = pick_village(eng)
    street_eng = pick_street(eng)

    easting = props.get("Easting")
    northing = props.get("Northing")
    district_chi = chi.get("ChiDistrict")
    district_eng = eng.get("EngDistrict")

    now = datetime.date.today().isoformat()

    row = {
        "id": csu or geoaddr or None,
        "geoaddress": geoaddr or None,
        "address_chi": text_normalize(address_chi),
        "address_eng": text_normalize(address_eng),
        # keep both combined and component fields
        "phase_chi": text_normalize(phase_chi),
        "block_chi": text_normalize(block_chi),
        "building_chi": text_normalize(building_chi),
        "estate_chi": text_normalize(estate_chi),
        "village_chi": text_normalize(village_chi),
        "street_chi": text_normalize(street_chi),
        "phase_eng": text_normalize(phase_eng),
        "block_eng": text_normalize(block_eng),
        "building_eng": text_normalize(building_eng),
        "estate_eng": text_normalize(estate_eng),
        "village_eng": text_normalize(village_eng),
        "street_eng": text_normalize(street_eng),
        "lat": lat,
        "lon": lon,
        "easting": easting,
        "northing": northing,
        "district_chi": district_chi,
        "district_eng": district_eng,
        "source": source,
        "source_version": source_version,
        "tags": [],
        "last_modified": now,
    }
    return row


def process_files(
    paths: Iterable[Path],
    source: str = DEFAULT_SOURCE,
    source_version: Optional[str] = None,
) -> List[Dict[str, Any]]:
    # Collect features across all input files and deduplicate to building level
    # using the canonical `id` if available (CSU or GeoAddress) as a stable key.
    from collections import OrderedDict

    seen = OrderedDict()

    for p in paths:
        if not p.exists():
            continue
        raw = json.loads(p.read_text(encoding="utf8"))
        features = raw.get("features", [])
        for f in tqdm(features, desc=f"Processing {p.name}", unit="feature"):
            row = normalize_feature(f, source=source, source_version=source_version)

            # prefer stable id (CSU/GeoAddress) to dedupe building-level entries
            key = None
            if row.get("id"):
                key = f"id::{row.get('id')}"
            elif row.get("geoaddress"):
                key = f"geo::{row.get('geoaddress')}"
            else:
                # fallback: use coordinates and address text to attempt a stable key
                lat = row.get("lat")
                lon = row.get("lon")

                # Ensure lat/lon are scalars not lists; try to coerce from nested values
                def safe_scalar(x):
                    if x is None:
                        return None
                    if isinstance(x, (int, float)):
                        return float(x)
                    # if list-like, try first numeric entry
                    if isinstance(x, (list, tuple)) and x:
                        for v in x:
                            if isinstance(v, (int, float)):
                                return float(v)
                        # nested list: maybe [[lon,lat],...]
                        if isinstance(x[0], (list, tuple)) and len(x[0]) >= 2:
                            if isinstance(x[0][0], (int, float)):
                                return float(x[0][1]) if x[0][1] is not None else None
                    try:
                        return float(x)
                    except Exception:
                        return None

                lat_val = safe_scalar(lat)
                lon_val = safe_scalar(lon)
                adchi = row.get("address_chi") or ""
                adeng = row.get("address_eng") or ""
                if lat_val is not None and lon_val is not None:
                    key = f"coord::{lat_val:.6f},{lon_val:.6f}"
                else:
                    key = f"addr::{adchi}||{adeng}"

            # only keep the first occurrence for a given key
            if key not in seen:
                seen[key] = row

    # Strip fields that should not be present in the canonical output
    # keep address_chi/address_eng for searching; remove other internal-only fields
    strip_keys = {
        "tags",
        "source",
        "source_version",
        "last_modified",
        "geoaddress",
    }
    out_rows: List[Dict[str, Any]] = []
    for r in seen.values():
        rc = dict(r)
        for k in strip_keys:
            if k in rc:
                rc.pop(k)
        out_rows.append(rc)

    return out_rows


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in",
        dest="input",
        nargs="+",
        required=True,
        help="Input GeoJSON file(s) or glob patterns",
    )
    parser.add_argument(
        "--out", default="data/als_canonical.csv", help="Output file path"
    )
    parser.add_argument(
        "--format",
        default=DEFAULT_FORMAT,
        choices=["csv", "parquet", "jsonl"],
        help="Output format",
    )
    parser.add_argument(
        "--source", default=DEFAULT_SOURCE, help="Source string to include"
    )
    parser.add_argument(
        "--source-version",
        default=None,
        help="Source version (e.g., md5 or snapshot) to include",
    )
    args = parser.parse_args(argv)

    in_paths = []
    for pat in args.input:
        p = Path(pat)
        if p.is_dir():
            in_paths.extend(sorted(p.glob("**/*.geojson")))
        else:
            # expand glob
            in_paths.extend(sorted(map(Path, list(p.parent.glob(p.name)))))

    # Remove duplicates
    in_paths = sorted(set(in_paths))

    rows = process_files(
        in_paths, source=args.source, source_version=args.source_version
    )
    df = pd.DataFrame(rows)

    outp = Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "csv":
        df.to_csv(outp, index=False)
    elif args.format == "parquet":
        df.to_parquet(outp, index=False)
    else:
        # jsonl: newline-delimited JSON
        with outp.open("w", encoding="utf8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(rows)} rows to {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
