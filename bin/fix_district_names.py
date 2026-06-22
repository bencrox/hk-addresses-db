#!/usr/bin/env python3
"""
Fix and normalise district names in canonical datasets.

Reads a canonical dataset (CSV/parquet/jsonl) produced by
`bin/geojson_to_canonical.py`, normalises the `district`
fields and writes a new column `sub_district` containing the common short
names used in OSM/other exports.

Usage:
  python bin/fix_district_names.py --in data/als_canonical.csv --out data/als_canonical_fixed.csv
"""
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from tqdm import tqdm
import pandas as pd
import json
import math
from pathlib import Path

tqdm.pandas()


def _haversine_distance_m(lat1, lon1, lat2, lon2):
    # Haversine distance (meters)
    R = 6371000.0
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    dphi = math.radians(float(lat2) - float(lat1))
    dlambda = math.radians(float(lon2) - float(lon1))
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * (
        math.sin(dlambda / 2.0) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# OSM place= values that correspond to the colloquial locality names HK
# residents actually use (旺角 / 尖沙咀 / village names), as opposed to the
# administrative districts gov.hk's ALS data is tagged with. `city_district`
# is intentionally absent: no HK OSM element carries it.
DEFAULT_PLACE_TYPES = (
    "suburb",
    "quarter",
    "neighbourhood",
    "village",
    "town",
    "region",
)


def _split_combined_name(name: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Split an OSM combined `name` like '旺角 Mong Kok' into (zh, en).

    Used as a fallback when explicit name:zh / name:en tags are missing.
    Returns (None, None) when the value can't be confidently split.
    """
    if not name:
        return (None, None)
    import re

    m = re.match(r"^([一-鿿·]+)\s+([A-Za-z][A-Za-z0-9'’.\- ]+)$", name.strip())
    if m:
        return (m.group(1), m.group(2).strip())
    return (None, None)


def load_overpass_places(path: Path, place_types: Tuple[str, ...] = DEFAULT_PLACE_TYPES):
    """Load candidate locality nodes from an Overpass JSON dump.

    Returns a list of dicts with keys: lat, lon, zh_name, en_name, place, tags.
    Only picks elements whose `place` tag denotes a colloquial locality (see
    DEFAULT_PLACE_TYPES). Falls back to parsing the combined `name` tag when
    explicit name:zh / name:en are absent so we don't drop otherwise-valid
    labels.
    """
    if not path.exists():
        raise SystemExit(f"Overpass file not found: {path}")
    data = json.loads(path.read_text(encoding="utf8"))
    elements = data.get("elements", [])
    accepted = {p.lower() for p in place_types}
    out = []
    for el in elements:
        tags = el.get("tags") or {}

        place_tag = (tags.get("place") or "").lower()
        if place_tag not in accepted:
            continue

        # determine coordinates (nodes carry lat/lon; ways/relations a center)
        lat = lon = None
        if "lat" in el and "lon" in el:
            lat = el.get("lat")
            lon = el.get("lon")
        elif isinstance(el.get("center"), dict):
            lat = el["center"].get("lat")
            lon = el["center"].get("lon")
        if lat is None or lon is None:
            continue

        zh_name = tags.get("name:zh")
        en_name = tags.get("name:en")
        if not zh_name or not en_name:
            zh_fallback, en_fallback = _split_combined_name(tags.get("name"))
            zh_name = zh_name or zh_fallback
            en_name = en_name or en_fallback
        if not zh_name or not en_name:
            continue

        out.append(
            {
                "lat": float(lat),
                "lon": float(lon),
                "zh_name": zh_name,
                "en_name": en_name,
                "place": place_tag,
                "tags": tags,
            }
        )
    return out


DISTRICT_MAP = {
    # English forms (with and without 'DISTRICT')
    "CENTRAL & WESTERN": "Central & Western",
    "CENTRAL AND WESTERN": "Central & Western",
    "CENTRAL AND WESTERN DISTRICT": "Central & Western",
    "EASTERN": "Eastern",
    "EASTERN DISTRICT": "Eastern",
    "ISLANDS": "Islands",
    "ISLANDS DISTRICT": "Islands",
    "KOWLOON CITY": "Kowloon City",
    "KOWLOON CITY DISTRICT": "Kowloon City",
    "KWAI TSING": "Kwai Tsing",
    "KWAI TSING DISTRICT": "Kwai Tsing",
    "KWUN TONG": "Kwun Tong",
    "KWUN TONG DISTRICT": "Kwun Tong",
    "NORTH": "North",
    "NORTH DISTRICT": "North",
    "SAI KUNG": "Sai Kung",
    "SAI KUNG DISTRICT": "Sai Kung",
    "SHA TIN": "Sha Tin",
    "SHA TIN DISTRICT": "Sha Tin",
    "SHAM SHUI PO": "Sham Shui Po",
    "SHAM SHUI PO DISTRICT": "Sham Shui Po",
    "SOUTHERN": "Southern",
    "SOUTHERN DISTRICT": "Southern",
    "TAI PO": "Tai Po",
    "TAI PO DISTRICT": "Tai Po",
    "TSUEN WAN": "Tsuen Wan",
    "TSUEN WAN DISTRICT": "Tsuen Wan",
    "TUEN MUN": "Tuen Mun",
    "TUEN MUN DISTRICT": "Tuen Mun",
    "WAN CHAI": "Wan Chai",
    "WAN CHAI DISTRICT": "Wan Chai",
    "WONG TAI SIN": "Wong Tai Sin",
    "WONG TAI SIN DISTRICT": "Wong Tai Sin",
    "YAU TSIM MONG": "Yau Tsim Mong",
    "YAU TSIM MONG DISTRICT": "Yau Tsim Mong",
    "YUEN LONG": "Yuen Long",
    "YUEN LONG DISTRICT": "Yuen Long",
    # Chinese forms
    "中西區": "Central & Western",
    "東區": "Eastern",
    "離島區": "Islands",
    "九龍城區": "Kowloon City",
    "葵青區": "Kwai Tsing",
    "觀塘區": "Kwun Tong",
    "北區": "North",
    "西貢區": "Sai Kung",
    "沙田區": "Sha Tin",
    "深水埗區": "Sham Shui Po",
    "南區": "Southern",
    "大埔區": "Tai Po",
    "荃灣區": "Tsuen Wan",
    "屯門區": "Tuen Mun",
    "灣仔區": "Wan Chai",
    "黃大仙區": "Wong Tai Sin",
    "油尖旺區": "Yau Tsim Mong",
    "元朗區": "Yuen Long",
}


def map_district(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    key = str(s).strip().upper()
    # Some inputs have trailing/leading words like 'DISTRICT' or 'DIST.'
    key = key.replace("DIST.", "DISTRICT")
    # Try direct map
    if key in DISTRICT_MAP:
        return DISTRICT_MAP[key]
    # Try remove the word DISTRICT and lookup
    if key.endswith(" DISTRICT"):
        base = key[: -len(" DISTRICT")]
        if base in DISTRICT_MAP:
            return DISTRICT_MAP[base]
    # As a fallback, try to collapse whitespace and remove punctuation
    import re

    simple = re.sub(r"[^A-Z0-9\u4e00-\u9fff]+", " ", key).strip()
    if simple in DISTRICT_MAP:
        return DISTRICT_MAP[simple]
    # No mapping found; return None
    return None


def _nearest_localities(
    df: pd.DataFrame,
    places: List[Dict[str, Any]],
    max_m: float,
) -> pd.DataFrame:
    """Vectorised nearest-locality lookup.

    For every row with valid lat/lon, find the geographically nearest candidate
    locality within `max_m` metres. Uses a metric projection (HK80 / EPSG:2326)
    and geopandas' rtree-backed sjoin_nearest, so it is distance-first and runs
    in roughly O(n log n) rather than the old O(n_addresses * n_places) loop.

    Returns a DataFrame aligned to df.index with columns
    sub_district_chi, sub_district_eng, sub_district_dist_m.
    """
    import geopandas as gpd

    cols = ["sub_district_chi", "sub_district_eng", "sub_district_dist_m"]
    result = pd.DataFrame(index=df.index, columns=cols, dtype=object)

    if not places:
        return result

    valid = df["lat"].notna() & df["lon"].notna()
    if not valid.any():
        return result

    addr = gpd.GeoDataFrame(
        df.loc[valid, []],
        geometry=gpd.points_from_xy(df.loc[valid, "lon"], df.loc[valid, "lat"]),
        crs="EPSG:4326",
    ).to_crs(2326)

    pdf = pd.DataFrame(places)
    place_gdf = gpd.GeoDataFrame(
        pdf[["zh_name", "en_name"]],
        geometry=gpd.points_from_xy(pdf["lon"], pdf["lat"]),
        crs="EPSG:4326",
    ).to_crs(2326)

    joined = gpd.sjoin_nearest(
        addr, place_gdf, how="left", max_distance=float(max_m), distance_col="dist_m"
    )
    # sjoin_nearest can emit several rows for distance ties; keep the first.
    joined = joined[~joined.index.duplicated(keep="first")]

    result.loc[joined.index, "sub_district_chi"] = joined["zh_name"].values
    result.loc[joined.index, "sub_district_eng"] = joined["en_name"].values
    result.loc[joined.index, "sub_district_dist_m"] = joined["dist_m"].values
    return result


def _inject_sub_district(
    addr: Optional[str],
    district: Optional[str],
    sub_district: Optional[str],
    *,
    before_district: bool,
) -> Optional[str]:
    """Splice the colloquial sub_district into an address string.

    Anchors on the district token already present in the address. Chinese
    addresses run large->small so the locality goes *after* the district
    (...大埔區 太和...); English runs small->large so it goes *before*
    (...Tai Wo Tai Po District...). No-ops when the anchor is absent or the
    locality is already present, so it is safe to run repeatedly.
    """
    if not addr or pd.isna(sub_district) or not district or pd.isna(district):
        return addr
    if str(sub_district) in str(addr):
        return addr
    if str(district) not in str(addr):
        return addr
    if before_district:
        replacement = f"{sub_district} {district}"
    else:
        replacement = f"{district} {sub_district}"
    return str(addr).replace(str(district), replacement, 1)


def process_df(
    df: pd.DataFrame,
    places: Optional[List[Dict[str, Any]]] = None,
    max_m: float = 1500.0,
    prefer_als_village: bool = True,
    inject_into_address: bool = False,
) -> pd.DataFrame:
    """Normalise district names and derive a colloquial `sub_district`.

    Two-stage derivation:
      1. Geographic: nearest OSM locality label within `max_m` metres
         (see `_nearest_localities`).
      2. Tail fallback (`prefer_als_village`): for rows with no label inside the
         cap, reuse the village name the ALS record already carries — in the New
         Territories the village name *is* the colloquial locality.

    When `inject_into_address` is set, the derived locality is also spliced into
    the `address_chi` / `address_eng` strings next to the district token.
    """
    out = df.copy()

    if places is None:
        places = globals().get("_PLACES_LOADED")

    # Stage 1 — geographic nearest locality
    if places and {"lat", "lon"}.issubset(out.columns):
        nearest = _nearest_localities(out, places, max_m)
        out["sub_district_chi"] = nearest["sub_district_chi"]
        out["sub_district_eng"] = nearest["sub_district_eng"]
        out["sub_district_dist_m"] = nearest["sub_district_dist_m"]
    else:
        out["sub_district_chi"] = None
        out["sub_district_eng"] = None
        out["sub_district_dist_m"] = None

    # Stage 2 — fall back to the ALS village name where geography found nothing
    if prefer_als_village:
        if "village_chi" in out.columns:
            mask = out["sub_district_chi"].isna() & out["village_chi"].notna()
            out.loc[mask, "sub_district_chi"] = out.loc[mask, "village_chi"]
        if "village_eng" in out.columns:
            mask = out["sub_district_eng"].isna() & out["village_eng"].notna()
            out.loc[mask, "sub_district_eng"] = out.loc[mask, "village_eng"]

    # Optional — splice the locality into the address strings themselves
    if inject_into_address:
        if {"address_chi", "district_chi"}.issubset(out.columns):
            out["address_chi"] = [
                _inject_sub_district(a, d, s, before_district=False)
                for a, d, s in zip(
                    out["address_chi"], out["district_chi"], out["sub_district_chi"]
                )
            ]
        if {"address_eng", "district_eng"}.issubset(out.columns):
            out["address_eng"] = [
                _inject_sub_district(a, d, s, before_district=True)
                for a, d, s in zip(
                    out["address_eng"], out["district_eng"], out["sub_district_eng"]
                )
            ]

    return out


def load_input(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Input file not found: {path}")
    suf = path.suffix.lower()
    if suf == ".csv":
        return pd.read_csv(path)
    if suf in (".parquet", ".pq"):
        return pd.read_parquet(path)
    # default jsonl
    rows = []
    with path.open("r", encoding="utf8") as fh:
        for line in fh:
            rows.append(__import__("json").loads(line))
    return pd.DataFrame(rows)


def write_output(df: pd.DataFrame, path: Path) -> None:
    suf = path.suffix.lower()
    if suf == ".csv":
        df.to_csv(path, index=False)
    elif suf in (".parquet", ".pq"):
        df.to_parquet(path, index=False)
    else:
        # jsonl default
        with path.open("w", encoding="utf8") as fh:
            for _, r in df.iterrows():
                fh.write(
                    __import__("json").dumps(r.dropna().to_dict(), ensure_ascii=False)
                    + "\n"
                )


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--in", dest="input", required=True, help="Input canonical file"
    )
    parser.add_argument(
        "--out",
        dest="out",
        default=None,
        help="Output canonical file (defaults to input path with _fixed suffix)",
    )
    parser.add_argument(
        "--overpass",
        default=None,
        help="Path to Overpass JSON (e.g. data/overpass_places_913110.json) to match suburbs",
    )
    parser.add_argument(
        "--overpass-max-m",
        default=1500,
        type=float,
        help="Maximum distance in meters to accept nearest Overpass place as sub_district",
    )
    parser.add_argument(
        "--inject-into-address",
        action="store_true",
        help="Also splice the derived sub_district into the address_chi/eng strings",
    )

    args = parser.parse_args(argv)

    inp = Path(args.input)
    outp = (
        Path(args.out) if args.out else inp.with_name(inp.stem + "_fixed" + inp.suffix)
    )

    # optionally load overpass places
    if args.overpass:
        places = load_overpass_places(Path(args.overpass))
        globals()["_PLACES_LOADED"] = places
        globals()["_PLACES_MATCH_MAX_M"] = float(args.overpass_max_m)

    df = load_input(inp)
    df2 = process_df(
        df,
        places=globals().get("_PLACES_LOADED"),
        max_m=float(args.overpass_max_m),
        inject_into_address=args.inject_into_address,
    )
    write_output(df2, outp)
    print(f"Wrote {len(df2)} rows to {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
