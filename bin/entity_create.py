#!/usr/bin/env python3
"""
Scaffold a Markdown entity file with YAML frontmatter.

Usage: python bin/entity_create.py --slug tai_po --en "Tai Po" --zh "大埔" --category district --lat 22.45 --lon 114.17
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import datetime

ENT_DIR = Path("entities")


def slugify(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"[^\w\-\s]", "", t)
    t = re.sub(r"\s+", "-", t)
    return t


def scaffold(
    slug: str,
    en: str,
    zh: str,
    category: str,
    lat: float | None,
    lon: float | None,
    source: str | None,
):
    ENT_DIR.mkdir(parents=True, exist_ok=True)
    slug = slugify(slug)
    path = ENT_DIR / f"{slug}.md"
    if path.exists():
        raise SystemExit(f"Entity already exists: {path}")
    front = {
        "id": slug,
        "names": {"en": en, "zh": zh},
        "category": category,
        "lat": lat,
        "lon": lon,
        "source": source,
        "last_updated": datetime.date.today().isoformat(),
    }
    yaml = "---\n"
    for k, v in front.items():
        yaml += f"{k}: {v}\n"
    yaml += "---\n\n"
    body = f"# {en} ({zh})\n\n" + "Short description here.\n"
    path.write_text(yaml + body, encoding="utf8")
    print("Created entity file", path)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--slug", required=True)
    p.add_argument("--en", required=True)
    p.add_argument("--zh", default="")
    p.add_argument("--category", default="poi")
    p.add_argument("--lat", type=float, default=None)
    p.add_argument("--lon", type=float, default=None)
    p.add_argument("--source", default=None)
    args = p.parse_args()
    scaffold(
        args.slug, args.en, args.zh, args.category, args.lat, args.lon, args.source
    )
