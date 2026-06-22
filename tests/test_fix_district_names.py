import pandas as pd

from bin.fix_district_names import (
    map_district,
    process_df,
    _split_combined_name,
)


def test_map_district_chinese():
    assert map_district("沙田區") == "Sha Tin"


def test_map_district_english_varients():
    assert map_district("SHA TIN DISTRICT") == "Sha Tin"
    assert map_district("Sha Tin") == "Sha Tin"
    assert map_district("YUEN LONG DISTRICT") == "Yuen Long"


def test_split_combined_name():
    assert _split_combined_name("旺角 Mong Kok") == ("旺角", "Mong Kok")
    assert _split_combined_name("古洞 Kwu Tung") == ("古洞", "Kwu Tung")
    # Not confidently splittable -> (None, None)
    assert _split_combined_name("Mong Kok") == (None, None)
    assert _split_combined_name(None) == (None, None)


def _places():
    # zh/en bilingual locality labels, matching the real loader output shape
    return [
        {"lat": 22.5, "lon": 114.1, "zh_name": "上水", "en_name": "Sheung Shui", "place": "town"},
        {"lat": 22.45, "lon": 114.17, "zh_name": "大埔", "en_name": "Tai Po", "place": "suburb"},
    ]


def test_process_df_nearest_locality_distance_first():
    rows = [
        {"id": "p1", "lat": 22.499, "lon": 114.100},  # next to Sheung Shui
        {"id": "p2", "lat": 22.451, "lon": 114.171},  # next to Tai Po
    ]
    df = pd.DataFrame(rows)
    out = process_df(df, places=_places(), max_m=5000)
    assert out.loc[out.id == "p1", "sub_district_eng"].iloc[0] == "Sheung Shui"
    assert out.loc[out.id == "p1", "sub_district_chi"].iloc[0] == "上水"
    assert out.loc[out.id == "p2", "sub_district_eng"].iloc[0] == "Tai Po"


def test_process_df_respects_max_distance():
    # Address far from any label, with a tight cap -> no geographic match
    rows = [{"id": "far", "lat": 22.20, "lon": 113.90}]
    df = pd.DataFrame(rows)
    out = process_df(df, places=_places(), max_m=1500)
    assert pd.isna(out.loc[out.id == "far", "sub_district_eng"].iloc[0])


def test_process_df_village_fallback():
    # No nearby label within the cap, but the ALS record carries a village name.
    rows = [
        {
            "id": "v1",
            "lat": 22.20,
            "lon": 113.90,
            "village_chi": "錦田",
            "village_eng": "Kam Tin",
        }
    ]
    df = pd.DataFrame(rows)
    out = process_df(df, places=_places(), max_m=1500, prefer_als_village=True)
    assert out.loc[out.id == "v1", "sub_district_eng"].iloc[0] == "Kam Tin"
    assert out.loc[out.id == "v1", "sub_district_chi"].iloc[0] == "錦田"

    # Disabled -> stays empty
    out2 = process_df(df, places=_places(), max_m=1500, prefer_als_village=False)
    assert pd.isna(out2.loc[out2.id == "v1", "sub_district_eng"].iloc[0])


def test_process_df_inject_into_address():
    # Locality (太和 / Tai Wo) is distinct from the district token (大埔 / Tai Po)
    places = [
        {"lat": 22.451, "lon": 114.171, "zh_name": "太和", "en_name": "Tai Wo", "place": "suburb"},
    ]
    rows = [
        {
            "id": "i1",
            "lat": 22.451,
            "lon": 114.171,
            "address_chi": "新界大埔區某街1號",
            "district_chi": "大埔區",
            "address_eng": "1 Some Street, Tai Po District, New Territories",
            "district_eng": "Tai Po District",
        }
    ]
    df = pd.DataFrame(rows)
    out = process_df(df, places=places, max_m=5000, inject_into_address=True)
    r = out.loc[out.id == "i1"].iloc[0]
    # Chinese: locality after the district token (large -> small)
    assert "大埔區 太和" in r["address_chi"]
    # English: locality before the district token (small -> large)
    assert "Tai Wo Tai Po District" in r["address_eng"]

    # Idempotent: running again does not double-insert
    out2 = process_df(out, places=places, max_m=5000, inject_into_address=True)
    assert out2.loc[out2.id == "i1", "address_eng"].iloc[0] == r["address_eng"]


def test_process_df_no_places_is_safe():
    df = pd.DataFrame([{"id": "a", "lat": 22.5, "lon": 114.1}])
    out = process_df(df, places=None)
    assert "sub_district_eng" in out.columns
    assert pd.isna(out.loc[out.id == "a", "sub_district_eng"].iloc[0])
