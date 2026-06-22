import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from bin.enrich_entity import enrich_entity, ENT_DIR, read_frontmatter


def test_enrich_entity_creates_file(tmp_path: Path, monkeypatch):
    # Prepare: patch search to return a fake result
    fake_result = {
        "display_name": "Tai Po, Hong Kong",
        "osm_type": "node",
        "osm_id": 1234,
        "class": "place",
    }

    monkeypatch.setattr(
        "bin.enrich_entity.search", lambda q, limit, polygon_geojson: [fake_result]
    )

    # patch fetch_details to return a basic details with address
    def fake_fetch(*args, **kwargs):
        return {
            "address": {"city": "Tai Po", "suburb": "Tai Po"},
            "geojson": {"type": "Point"},
        }

    monkeypatch.setattr("bin.enrich_entity.fetch_details", fake_fetch)

    # use tmp ENT_DIR
    monkeypatch.setattr("bin.enrich_entity.ENT_DIR", tmp_path)

    slug = "tai_po"
    # call enrich
    res = enrich_entity(
        slug, name="Tai Po", limit=1, fetch_geom=True, source_version="test-v1"
    )
    assert res["status"] == "ok"
    path = tmp_path / f"{slug}.md"
    assert path.exists()

    fm = read_frontmatter(path)
    assert fm["id"] == slug
    # tags include nominatim and nominatim-polygon
    assert "nominatim" in fm["tags"]
    assert "nominatim-polygon" in fm["tags"]
    assert fm.get("assigned_district") == "Tai Po"


def test_enrich_no_candidates(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "bin.enrich_entity.search", lambda q, limit, polygon_geojson: []
    )
    monkeypatch.setattr("bin.enrich_entity.ENT_DIR", tmp_path)
    res = enrich_entity("unknown_x")
    assert res["status"] == "no_candidates"
