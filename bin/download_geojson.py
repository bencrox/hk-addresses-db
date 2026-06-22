#!/usr/bin/env python3
"""
Download and manage gov.hk ALS-GeoJSON zip archive.

Features:
- Downloads to specified output directory
- Checks if the remote file changed using ETag/Last-Modified/Content-Length
- Saves metadata to avoid re-downloading unchanged files
- Optional unzip
- Optional inspection summary to list GeoJSON filenames

Usage:
    python bin/download_geojson.py --output data --unzip

"""

from __future__ import annotations
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

import requests

DEFAULT_URL = "https://res.data.gov.hk/api/get-download-file?name=https%3A%2F%2Fwww.als.gov.hk%2Fdata%2FALS-GeoJSON.zip"
METADATA_NAME = "ALS-GeoJSON.metadata.json"


def get_remote_head(url: str) -> dict:
    r = requests.head(url, allow_redirects=True)
    r.raise_for_status()
    return {
        "etag": r.headers.get("ETag"),
        "last_modified": r.headers.get("Last-Modified"),
        "content_length": r.headers.get("Content-Length"),
        "status_code": r.status_code,
        "url": r.url,
    }


def save_metadata(path: Path, meta: dict):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)


def load_metadata(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def stream_download(url: str, dest: Path) -> None:
    # stream to temporary file first
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    tmp.write(chunk)
            tmp.flush()
            tmp_name = Path(tmp.name)
    shutil.move(str(tmp_name), str(dest))


def extract_zip(zip_path: Path, dest_dir: Path) -> None:
    import zipfile

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(dest_dir)


def summarize_download(dest_dir: Path):
    # Simple summary: list files under dest_dir, counts of .geojson
    files = list(dest_dir.rglob("*"))
    geojsons = [f for f in files if f.suffix.lower() == ".geojson"]
    print(f"Files in {dest_dir}: {len(files)}")
    print(f"GeoJSON files: {len(geojsons)}")
    if geojsons:
        print("Examples:")
        for f in geojsons[:10]:
            print(" - ", f.relative_to(dest_dir))


def inspect_properties(dest_dir: Path):
    """Walk all .geojson files, print feature counts and property keys with frequencies."""
    import json

    files = [p for p in dest_dir.rglob("*.geojson")]
    overall_keys = {}
    total_features = 0
    for p in files:
        with open(p, "r", encoding="utf-8") as fh:
            gj = json.load(fh)
        features = gj.get("features", [])
        total_features += len(features)
        keys_seen = {}
        for feat in features:
            props = feat.get("properties", {})
            for k in props.keys():
                keys_seen[k] = keys_seen.get(k, 0) + 1
        print(
            f"File: {p.relative_to(dest_dir)} — features={len(features)} keys={len(keys_seen)}"
        )
        # Print top 10 keys in this file
        top_local = sorted(keys_seen.items(), key=lambda x: -x[1])[:10]
        for k, cnt in top_local:
            print(f"  {k}: {cnt}")
        for k, cnt in keys_seen.items():
            overall_keys[k] = overall_keys.get(k, 0) + cnt

    print("\nOverall Dataset Summary:")
    print(f"Total GeoJSON files: {len(files)}")
    print(f"Total features: {total_features}")
    top_global = sorted(overall_keys.items(), key=lambda x: -x[1])[:40]
    print("Top property keys (global):")
    for k, cnt in top_global:
        print(f"  {k}: {cnt}")


def compute_file_hash(path: Path) -> str:
    md5 = hashlib.md5()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(8192)
            if not chunk:
                break
            md5.update(chunk)
    return md5.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL, help="Download URL")
    parser.add_argument("--output", default="data", help="Output directory")
    parser.add_argument("--unzip", action="store_true", help="Unzip downloaded file")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if remote hasn't changed",
    )
    parser.add_argument(
        "--inspect", action="store_true", help="Show a summary of the extracted files"
    )
    parser.add_argument(
        "--inspect-properties",
        action="store_true",
        help="Inspect property keys and frequencies in GeoJSON files",
    )
    parser.add_argument(
        "--metadata",
        default=METADATA_NAME,
        help="Metadata filename to store remote ETag/Last-Modified",
    )
    args = parser.parse_args()

    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)

    zip_name = Path(args.url.split("?")[0].split("/")[-1])
    # Ensure zip_name sensible
    if not zip_name.suffix:
        zip_name = Path("ALS-GeoJSON.zip")

    dest_zip = outdir / zip_name
    meta_path = outdir / args.metadata

    print(f"HEAD {args.url} ...")
    remote_head = get_remote_head(args.url)
    print("Remote metadata:")
    print(json.dumps(remote_head, indent=2))

    local_meta = load_metadata(meta_path)
    if local_meta:
        print("Local metadata:")
        print(json.dumps(local_meta, indent=2))

    if not args.force and local_meta:
        remote_signature = (
            remote_head.get("etag"),
            remote_head.get("last_modified"),
            remote_head.get("content_length"),
        )
        local_signature = (
            local_meta.get("etag"),
            local_meta.get("last_modified"),
            str(local_meta.get("content_length")),
        )
        if remote_signature == local_signature and dest_zip.exists():
            print(
                "No changes detected in remote file — skipping download. Use --force to re-download."
            )
            if args.inspect or args.unzip:
                if args.unzip:
                    extract_zip(dest_zip, outdir)
                if args.inspect:
                    summarize_download(outdir)
            return

    print("Downloading...")
    stream_download(args.url, dest_zip)
    print("Downloaded to", dest_zip)

    file_hash = compute_file_hash(dest_zip)
    print("Downloaded file md5:", file_hash)

    # Save metadata
    new_meta = {
        "url": remote_head.get("url"),
        "etag": remote_head.get("etag"),
        "last_modified": remote_head.get("last_modified"),
        "content_length": remote_head.get("content_length"),
        "file_md5": file_hash,
        "downloaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "file_name": str(dest_zip.name),
    }
    save_metadata(meta_path, new_meta)
    print("Saved metadata to", meta_path)

    if args.unzip:
        print("Unzipping to", outdir)
        extract_zip(dest_zip, outdir)

    if args.inspect:
        summarize_download(outdir)
    if args.inspect_properties:
        inspect_properties(outdir)

    print("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Error:", exc, file=sys.stderr)
        sys.exit(2)
