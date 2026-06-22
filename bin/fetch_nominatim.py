#!/usr/bin/env python3
"""
Fetch Nominatim details for a specific OSM element (using osmtype and osmid).
Example:
  https://nominatim.openstreetmap.org/details?osmtype=N&osmid=4793044337&class=railway&addressdetails=1&entrances=1&hierarchy=0&group_hierarchy=1&format=json

Usage:
  python bin/fetch_nominatim.py --osmtype N --osmid 4793044337 --class railway --out data/details_4793044337.json
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from typing import Optional
import requests
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

NOMINATIM_DETAILS_URL = "https://nominatim.openstreetmap.org/details"
CACHE_PATH_DEFAULT = Path("data/nominatim_details_cache.json")
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


def fetch_details(
    osmtype: str,
    osmid: int,
    c: Optional[str] = None,
    addressdetails: int = 1,
    entrances: Optional[int] = None,
    hierarchy: int = 0,
    group_hierarchy: int = 1,
    user_agent: str = DEFAULT_USER_AGENT,
):
    params = {
        "osmtype": osmtype,
        "osmid": osmid,
        "format": "json",
        "addressdetails": addressdetails,
        "hierarchy": hierarchy,
        "group_hierarchy": group_hierarchy,
    }
    if c:
        params["class"] = c
    if entrances is not None:
        params["entrances"] = entrances
    headers = {"User-Agent": user_agent}
    r = requests.get(NOMINATIM_DETAILS_URL, params=params, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--osmtype",
        choices=["N", "W", "R"],
        required=True,
        help="OSM type: N=node, W=way, R=relation",
    )
    p.add_argument("--osmid", type=int, required=True)
    p.add_argument(
        "--class",
        default=None,
        dest="cls",
        help="Restrict class (e.g., railway, boundary)",
    )
    p.add_argument("--addressdetails", type=int, default=1)
    p.add_argument("--entrances", type=int, default=None)
    p.add_argument("--out", default=None, help="Output filepath for JSON")
    p.add_argument(
        "--cache", default=str(CACHE_PATH_DEFAULT), help="Path to cache file"
    )
    p.add_argument("--force", action="store_true", help="Ignore cache")
    p.add_argument(
        "--sleep", default=1.0, type=float, help="Seconds to sleep for rate limiting"
    )
    args = p.parse_args()

    cache_path = Path(args.cache)
    cache = load_cache(cache_path)
    key = f"details::{args.osmtype}::{args.osmid}::cls={args.cls or ''}::entr={args.entrances or ''}"

    if key in cache and not args.force:
        print("Loaded cached details for", key)
        details = cache[key]
    else:
        print("Fetching details for", key)
        try:
            # create a geopy Nominatim object to ensure we have a polite user-agent
            # (we still use the details endpoint via requests, so pass the same user-agent)
            geolocator = Nominatim(user_agent=DEFAULT_USER_AGENT)
            details = fetch_details(
                args.osmtype,
                args.osmid,
                c=args.cls,
                addressdetails=args.addressdetails,
                entrances=args.entrances,
                user_agent=DEFAULT_USER_AGENT,
            )
        except GeocoderTimedOut:
            print("Nominatim timed out while fetching details")
            details = {}
        except requests.RequestException as e:
            print("Failed to fetch nominatim details:", e)
            details = {}
        cache[key] = details
        save_cache(cache, cache_path)
        time.sleep(args.sleep)

    if args.out:
        outp = Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(
            json.dumps(details, ensure_ascii=False, indent=2), encoding="utf8"
        )
        print("Saved", outp)
    else:
        print(json.dumps(details, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
