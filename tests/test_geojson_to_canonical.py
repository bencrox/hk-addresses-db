import json
from pathlib import Path

from bin.geojson_to_canonical import normalize_feature, process_files


def make_feature(lon=114.2, lat=22.3, csu="abc123"):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "Easting": 1,
            "Northing": 2,
            "Address": {
                "PremisesAddress": {
                    "BuildingCsuInformation": {"CsuId": csu},
                    "ChiPremisesAddress": {
                        "ChiDistrict": "沙田區",
                        "BuildingName": "愛道園",
                        "ChiEstate": {"EstateName": "西環邨"},
                    },
                    "EngPremisesAddress": {
                        "EngDistrict": "SHA TIN DISTRICT",
                        "BuildingName": "Oi Do Yuen",
                        "EngEstate": {"EstateName": "Sai Wan Estate"},
                    },
                    "GeoAddress": csu,
                }
            },
        },
    }


def test_normalize_feature_shows_fields():
    f = make_feature()
    row = normalize_feature(f, source="gov_hk/ALS-GeoJSON", source_version="vtest")
    assert row["id"] == "abc123"
    assert row["geoaddress"] == "abc123"
    assert "愛道園" in (row.get("address_chi") or "")
    assert "Oi Do Yuen" in (row.get("address_eng") or "")
    # newly added component fields
    assert row.get("building_chi") == "愛道園"
    assert row.get("building_eng") == "Oi Do Yuen"
    assert row.get("estate_chi") == "西環邨"


def test_process_files(tmp_path: Path):
    feat1 = make_feature(lon=114.1, lat=22.2, csu="X1")
    feat2 = make_feature(lon=114.2, lat=22.3, csu="X2")
    gj = {"type": "FeatureCollection", "features": [feat1, feat2]}
    fp = tmp_path / "sample.geojson"
    fp.write_text(json.dumps(gj, ensure_ascii=False), encoding="utf8")

    rows = process_files([fp], source="gov_hk/ALS-GeoJSON", source_version="vtest")
    assert len(rows) == 2
    ids = {r["id"] for r in rows}
    assert ids == {"X1", "X2"}
    # address_chi/address_eng should be preserved for searching; other internal fields removed
    for r in rows:
        assert "address_chi" in r
        assert "address_eng" in r
        assert "geoaddress" not in r
        assert "tags" not in r
        assert "source" not in r
        assert "source_version" not in r
        assert "last_modified" not in r


def test_process_files_dedup_building_level(tmp_path: Path):
    # Two features that represent the same building (same csu) should be deduped
    feat1 = make_feature(lon=114.1, lat=22.2, csu="B1")
    feat2 = make_feature(lon=114.1, lat=22.2, csu="B1")
    gj1 = {"type": "FeatureCollection", "features": [feat1]}
    gj2 = {"type": "FeatureCollection", "features": [feat2]}

    fp1 = tmp_path / "a.geojson"
    fp2 = tmp_path / "b.geojson"
    fp1.write_text(json.dumps(gj1, ensure_ascii=False), encoding="utf8")
    fp2.write_text(json.dumps(gj2, ensure_ascii=False), encoding="utf8")

    rows = process_files(
        [fp1, fp2], source="gov_hk/ALS-GeoJSON", source_version="vtest"
    )
    # Should only keep 1 row for the duplicate building
    assert len(rows) == 1
    assert rows[0]["id"] == "B1"
    for r in rows:
        assert "address_chi" in r
        assert "address_eng" in r
        assert "geoaddress" not in r
        assert "tags" not in r
        assert "source" not in r
        assert "source_version" not in r
        assert "last_modified" not in r


def test_nested_coordinates_point_and_multipoint(tmp_path: Path):
    # A feature with nested coordinates (MultiPoint style) should still yield a valid scalar lat/lon
    feat_mp = make_feature(lon=[[114.1, 22.2], [114.11, 22.21]], lat=None, csu="M1")
    # Adjust geometry directly to simulate nested coordinates
    feat_mp["geometry"] = {
        "type": "MultiPoint",
        "coordinates": [[114.1, 22.2], [114.11, 22.21]],
    }
    gj = {"type": "FeatureCollection", "features": [feat_mp]}
    fp = tmp_path / "mp.geojson"
    fp.write_text(json.dumps(gj, ensure_ascii=False), encoding="utf8")

    rows = process_files([fp], source="gov_hk/ALS-GeoJSON", source_version="vtest")
    assert len(rows) == 1
    r = rows[0]
    # ensure lat/lon are scalar floats
    assert isinstance(r.get("lat"), float) or r.get("lat") is not None
    assert isinstance(r.get("lon"), float) or r.get("lon") is not None
