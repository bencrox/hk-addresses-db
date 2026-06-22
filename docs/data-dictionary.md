# Data Dictionary — HK Addresses Canonical Dataset

This document describes the fields of the canonical Hong Kong address dataset,
`data/als_canonical_fixed.csv` (159,416 rows, 24 columns, UTF-8 encoded).

Each row is one address record. Bilingual fields come in `*_chi` (Traditional
Chinese) and `*_eng` (English) pairs. Fill rates below are for the current
release and reflect that many ALS records only populate a subset of address
components (e.g. a record is either street-based *or* estate-based).

## Provenance

| Source | Role |
| --- | --- |
| gov.hk **ALS** (Address Lookup Service) GeoJSON | Primary source for every address record, identifiers, coordinates, and administrative district. |
| **OpenStreetMap** (via Overpass) | Source for the colloquial `sub_district` locality names. |

Pipeline: `geojson_to_canonical.py` → `fix_district_names.py`. See the
[README](../README.md) for the full build process.

## Fields

### Identity

| Field | Type | Fill | Description |
| --- | --- | --- | --- |
| `id` | string | 100% | Stable record identifier from ALS — the CSU (Centralised Spatial Unit) reference, falling back to the GeoAddress key. Used to deduplicate building-level entries. |

### Full address (composed)

| Field | Type | Fill | Description |
| --- | --- | --- | --- |
| `address_chi` | string | 100% | Full Chinese address, composed large→small: `region · district · sub_district · street · number · building`. |
| `address_eng` | string | 100% | Full English address, composed small→large: `building · number · street · sub_district · district · region`. |

> If the dataset was built with `--inject-into-address`, the colloquial
> `sub_district` is spliced into these strings next to the district token
> (Chinese: after the district; English: before it). Without that flag the
> address strings carry only the administrative district.

### Address components

Bilingual component pairs extracted from the ALS structured address. Each is
null when the record does not use that component.

| Field (chi / eng) | Type | Fill | Description |
| --- | --- | --- | --- |
| `building_chi` / `building_eng` | string | 17.2% / 17.5% | Building or premises name (e.g. `OHEL LEAH SYNAGOGUE`). |
| `block_chi` / `block_eng` | string | 12.7% | Block designation within an estate/building (e.g. `A`). |
| `phase_chi` / `phase_eng` | string | 0% | Estate development phase name. Present in the schema for completeness; unpopulated in the current ALS release. |
| `estate_chi` / `estate_eng` | string | 21.7% / 21.8% | Estate or development name. |
| `village_chi` / `village_eng` | string | 60.4% | Village name. In the New Territories this is effectively the colloquial locality, and is used as the `sub_district` fallback (see below). |
| `street_chi` / `street_eng` | string | 39.4% | Street name (paired with the building number embedded in the full address). |

### Location

| Field | Type | Fill | Description |
| --- | --- | --- | --- |
| `lat` | float | 100% | Latitude, WGS 84 (EPSG:4326). |
| `lon` | float | 100% | Longitude, WGS 84 (EPSG:4326). |
| `easting` | float | 100% | Easting in the HK 1980 Grid (EPSG:2326), metres — as supplied by ALS. |
| `northing` | float | 100% | Northing in the HK 1980 Grid (EPSG:2326), metres — as supplied by ALS. |

### Administrative & colloquial area

| Field | Type | Fill | Description |
| --- | --- | --- | --- |
| `district_chi` | string | 100% | One of Hong Kong's 18 administrative districts, Chinese (e.g. `油尖旺區`). From ALS. |
| `district_eng` | string | 100% | Administrative district, English, normalised to a canonical spelling (e.g. `YAU TSIM MONG DISTRICT`). |
| `sub_district_chi` | string | 99.8% | **Colloquial locality name** people actually use, Chinese (e.g. `旺角`, `油麻地`). Derived, not from ALS — see below. |
| `sub_district_eng` | string | 99.8% | Colloquial locality name, English (e.g. `Mong Kok`, `Yau Ma Tei`). |
| `sub_district_dist_m` | float | 98.8% | Distance in metres from the address to the OSM locality label that produced `sub_district`. Null when the value came from the village fallback rather than a geographic match. Use it as a confidence signal — smaller is more reliable. |

## How `sub_district` is derived

The ALS data only tags addresses with the 18 administrative districts (e.g.
`油尖旺區`), which nobody uses conversationally. The `sub_district` fields add the
locality name residents actually say (`旺角`, `尖沙咀`, `油麻地`):

1. **Geographic match (98.8% of rows):** the nearest OpenStreetMap locality
   label (`place` = suburb / quarter / neighbourhood / village / town / region)
   within **1,500 m** of the address, measured in the HK 1980 metric projection.
   The distance is recorded in `sub_district_dist_m`.
2. **Village fallback (~1% of rows):** where no label is within range, the ALS
   `village` name on the record is used instead (it is the colloquial locality
   in rural areas). These rows have a null `sub_district_dist_m`.

About 0.2% of rows have neither and leave `sub_district` null.

## Coordinate reference systems

- `lat` / `lon`: **WGS 84 — EPSG:4326** (decimal degrees).
- `easting` / `northing`: **HK 1980 Grid — EPSG:2326** (metres).

## Licensing & attribution

This dataset is derived from two openly licensed sources and inherits their
attribution requirements:

- Address records, identifiers, coordinates and districts: **gov.hk Address
  Lookup Service**, under the [Digital Standards / data.gov.hk terms of use](https://data.gov.hk/en/terms-and-conditions).
- `sub_district` locality names: **© OpenStreetMap contributors**, under the
  [Open Database License (ODbL)](https://www.openstreetmap.org/copyright).

Any publication of this dataset must credit both sources accordingly.
