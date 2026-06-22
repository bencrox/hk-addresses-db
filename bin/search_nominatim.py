#!/usr/bin/env python3
"""
Search Nominatim for places and save the JSON results.

Usage examples:
  python bin/search_nominatim.py --q "Tai Po" --limit 5 --polygon --out data/search_tai_po.json
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from typing import Optional
from geopy.geocoders import Nominatim
from geopy.exc import (
    GeocoderTimedOut,
    GeocoderInsufficientPrivileges,
    GeocoderServiceError,
)

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
CACHE_PATH_DEFAULT = Path("data/nominatim_search_cache.json")
DEFAULT_USER_AGENT = "hk-addresses-db/1.0 (your_email@example.com)"


def load_cache(cache_path: Path) -> dict:
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf8"))
    except Exception:
        return {}


def save_cache(cache: dict, cache_path: Path):
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf8"
    )


def search(
    q: str,
    limit: int = 10,
    polygon_geojson: bool = False,
    countrycodes: Optional[str] = None,
    user_agent: str = DEFAULT_USER_AGENT,
):
    """Search via geopy.Nominatim and return raw result dicts (like Nominatim JSON).

    Different geopy versions accept different keyword names; try a few compatible
    parameter combinations and return the first successful result. If the
    geocoding service is unreachable or rejects the request, return an empty
    list.
    """
    geolocator = Nominatim(user_agent=user_agent)

    attempts = [
        {
            "exactly_one": False,
            "limit": limit,
            "addressdetails": True,
            "namedetails": True,
            "polygon_geojson": int(bool(polygon_geojson)),
            "countrycodes": countrycodes,
        },
        {
            "exactly_one": False,
            "limit": limit,
            "addressdetails": True,
            "namedetails": True,
            "polygon_geojson": int(bool(polygon_geojson)),
            "country_codes": countrycodes,
        },
        {
            "exactly_one": False,
            "limit": limit,
            "addressdetails": True,
            "namedetails": True,
            "country_codes": countrycodes,
        },
        {"exactly_one": False, "limit": limit},
    ]

    raw_results = None
    for params in attempts:
        try:
            raw_results = geolocator.geocode(q, **params)
            break
        except TypeError:
            # param not supported by this version of geopy - try next
            continue
        except GeocoderTimedOut:
            # timeouts treated as empty results
            return []
        except (GeocoderInsufficientPrivileges, GeocoderServiceError) as e:
            # API error/403 etc. - return empty and log the cause
            print("Geocoder error from Nominatim:", e)
            return []

    if not raw_results:
        return []

    out = []
    for loc in raw_results:
        if hasattr(loc, "raw") and isinstance(loc.raw, dict):
            out.append(loc.raw)
        else:
            out.append({"display_name": str(loc)})
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--q", required=True, help="Search text")
    p.add_argument("--limit", default=10, type=int)
    p.add_argument(
        "--polygon", action="store_true", help="Request polygon GeoJSON in results"
    )
    p.add_argument(
        "--countrycodes",
        default=None,
        help="Comma-separated country codes to limit search",
    )
    p.add_argument("--out", default=None, help="Path to save JSON output")
    p.add_argument(
        "--cache", default=str(CACHE_PATH_DEFAULT), help="Path to cache file"
    )
    p.add_argument("--force", action="store_true", help="Ignore cache and re-run")
    p.add_argument(
        "--sleep", default=1.0, type=float, help="Seconds to sleep for rate limiting"
    )
    args = p.parse_args()

    cache_path = Path(args.cache)
    cache = load_cache(cache_path)
    cache_key = f"search::{args.q}::limit={args.limit}::polygon={int(args.polygon)}::cc={args.countrycodes or ''}"

    if cache_key in cache and not args.force:
        print("Loaded cached results for", args.q)
        results = cache[cache_key]
    else:
        print("Querying Nominatim for", args.q)
        results = search(
            args.q,
            limit=args.limit,
            polygon_geojson=args.polygon,
            countrycodes=args.countrycodes,
        )
        cache[cache_key] = results
        save_cache(cache, cache_path)
        time.sleep(args.sleep)

    if args.out:
        outp = Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf8"
        )
        print("Saved", outp)
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
