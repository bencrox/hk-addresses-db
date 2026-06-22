#!/usr/bin/env python3
"""
Suggest new entities based on ALS-GeoJSON: find place names or estate names not present in `entities/` and print issue text.

This script is helpful for Manager Agent to see candidate entities and create issues.
"""
from __future__ import annotations
import json
from pathlib import Path
import argparse
import re

ENT_DIR = Path("entities")
DATA_DIR = Path("data")


def slugify(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"[^\w\-\s]", "", t)
    t = re.sub(r"\s+", "-", t)
    return t


def known_slugs():
    if not ENT_DIR.exists():
        return set()
    return set(p.stem for p in ENT_DIR.glob("*.md"))


def extract_candidates_from_als():
    # look for Address.PremisesAddress.CHI/ENG village or building name. Also look for simple name strings.
    candidates = set()
    for gj in DATA_DIR.glob("als_addresses_*.geojson"):
        with gj.open("r", encoding="utf8") as fh:
            doc = json.load(fh)
        for feat in doc.get("features", []):
            props = feat.get("properties", {})
            if not props:
                continue
            addr = props.get("Address") or props
            if isinstance(addr, dict):
                chi = (
                    addr.get("PremisesAddress", {})
                    .get("ChiPremisesAddress", {})
                    .get("ChiVillag")
                )
                chi2 = None
                # try to find village or building name fields generically
                # Note: ALS schema has nested structure; we will look for common sub-keys
                # fallback: try to look for EngPremisesAddress EngVillage VillageName
                try:
                    chi = (
                        addr.get("PremisesAddress", {})
                        .get("ChiPremisesAddress", {})
                        .get("ChiVillage", {})
                        .get("VillageName")
                    )
                except Exception:
                    chi = None
                if chi:
                    candidates.add(chi)
                try:
                    eng = (
                        addr.get("PremisesAddress", {})
                        .get("EngPremisesAddress", {})
                        .get("EngVillage", {})
                        .get("VillageName")
                    )
                except Exception:
                    eng = None
                if eng:
                    candidates.add(eng)
            else:
                # if Address string, use a simple tokenization rule to find building or estate names (rough)
                s = str(addr)
                # naive extract: words before word 'Estate' or 'Court' etc
                m = re.search(
                    r"([A-Za-z0-9\s]+(?:Estate|Court|Garden|Centre|Mansion|Plaza|Tower))",
                    s,
                )
                if m:
                    candidates.add(m.group(1).strip())
    return candidates


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--print", action="store_true")
    args = p.parse_args()

    existing = known_slugs()
    candidates = extract_candidates_from_als()

    suggestions = []
    for c in candidates:
        s = slugify(c)
        if s not in existing:
            suggestions.append((c, s))

    for c, s in suggestions[:200]:
        print("---")
        print("Candidate:", c)
        print("Suggested slug:", s)
        print("Issue template:\n")
        print("Title:", f"Entity Create: {c}")
        print("Body:")
        print("Entity name (EN / ZH):", c)
        print("Entity category: estate or poi")
        print("Short description:")
        print("Lat, Lon:")
        print("Source: gov.hk ALS-GeoJSON")
        print("Suggested slug / id:", s)


if __name__ == "__main__":
    main()
