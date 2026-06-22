#!/usr/bin/env python3
"""
Query Overpass for ALL elements with a 'name' tag inside an OSM entity
(relation by default) and save results as JSON.

WARNING: This query is extremely broad and is highly likely to fail on large,
densely mapped areas like Hong Kong due to Overpass API memory and timeout limits.

Example:
  python bin/export_places_os.py --osmid 913110 --out data/hk_all_named_elements.json
"""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path
from typing import List, Optional

import requests

DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
# Ensure you update this with your contact information to comply with Overpass usage policy
DEFAULT_USER_AGENT = "hk-addresses-db/1.0 (your_email@example.com)"


def area_id_for_relation(rel_id: int) -> int:
    # Overpass area id for a relation = 3600000000 + relation id
    return 3600000000 + int(rel_id)


def build_overpass_query(
    area_id: int, types: List[str], timeout: int = 300
) -> str:
    """Build a targeted Overpass query filtered to specific tag types.

    Each entry in `types` is either a bare key (e.g. "place" -> ["place"]) or a
    "key=value" pair (e.g. "railway=station" -> ["railway"="station"]). This is
    the narrower, more reliable alternative to `build_broad_query`, which fetches
    every named element and often exceeds Overpass resource limits.
    """
    query = f"[out:json][timeout:{int(timeout)}];\n"
    query += f"area({area_id})->.a;\n"
    query += "(\n"
    for t in types:
        if "=" in t:
            key, value = t.split("=", 1)
            query += f'  nwr["{key}"="{value}"](area.a);\n'
        else:
            query += f'  nwr["{t}"](area.a);\n'
    query += ");\n"
    query += "out geom;\n"
    return query


def build_broad_query(area_id: int, timeout: int = 300) -> str:
    """
    Implements the requested broad query: fetch all elements with a 'name' tag
    within the area, returning geometry.
    """
    query = f"[out:json][timeout:{int(timeout)}];\n"
    query += f"area({area_id})->.searchArea;\n"

    # Fetch all nodes, ways, and relations that have a name tag inside the area
    query += "nwr[name](area.searchArea);\n"

    # Request geometry for all elements
    query += "out geom;\n"

    return query


def fetch_overpass(
    overpass_url: str, query: str, user_agent: str, timeout: int = 180
) -> dict:
    headers = {"User-Agent": user_agent}
    r = requests.post(
        overpass_url, data=query.encode("utf8"), headers=headers, timeout=timeout
    )
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        # Provide useful debug output (trimmed to avoid huge dumps)
        body = r.text
        short = body[:2000] + ("..." if len(body) > 2000 else "")
        raise requests.HTTPError(f"{e} - response body:\n{short}") from e
    return r.json()


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--osmid",
        type=int,
        default="913110",  # Hong Kong
        help="OSM ID of the entity (relation id recommended)",
    )
    p.add_argument(
        "--osmtype",
        choices=["N", "W", "R"],
        default="R",
        help="OSM element type (default: R=relation)",
    )
    p.add_argument(
        "--overpass-url", default=DEFAULT_OVERPASS_URL, help="Overpass API URL"
    )
    p.add_argument(
        "--out", default="data/address_data.json", help="Output JSON file path"
    )
    p.add_argument(
        "--sleep",
        default=1.0,
        type=float,
        help="Seconds to sleep after fetching (rate limit)",
    )
    p.add_argument(
        "--timeout",
        default=300,  # Increased default timeout for the complex query
        type=int,
        help="Overpass request timeout in seconds (passed to requests)",
    )
    args = p.parse_args(argv)

    if args.osmtype != "R":
        print(
            "Note: area queries typically work with relation areas. Using provided osmtype but area mapping might not be exact."
        )

    area_id = area_id_for_relation(args.osmid)

    # --------------------------------------------------------
    # STEP 1: Execute Broad Query (All Named Elements)
    # --------------------------------------------------------

    print("=" * 70)
    print("⚠️ WARNING: Running extremely broad query (nwr[name]) for a large area.")
    print("This query is highly likely to fail due to Overpass API resource limits.")
    print("=" * 70)

    query = build_broad_query(area_id, timeout=args.timeout)
    print("Running Broad Query...")

    try:
        final_res = fetch_overpass(
            args.overpass_url, query, DEFAULT_USER_AGENT, timeout=args.timeout
        )
    except Exception as exc:
        print("Overpass Broad Query failed:", exc)
        return 2

    elements_count = len(final_res.get("elements", []))
    print(f"Total elements fetched: {elements_count}")

    # Save the final JSON file
    if args.out:
        outp = Path(args.out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(
            json.dumps(final_res, ensure_ascii=False, indent=2), encoding="utf8"
        )
        print("Saved results to", outp)

    # Check for empty result after successful fetch (common failure mode)
    if elements_count == 0 and len(final_res.keys()) > 2:
        print("\nSUCCESSFUL FETCH, BUT ZERO ELEMENTS RETURNED.")
        print(
            "This confirms the query was too broad and exceeded the server's resource limits."
        )
        print("Consider reverting to the previous multi-step query approach.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
