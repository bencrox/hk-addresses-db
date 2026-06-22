import argparse
import json
import geopandas as gpd
from shapely.geometry import Polygon, Point
import os

# --- Function 1: Load and Separate Data ---


def process_osm_elements(elements):
    # ... (initializations)
    building_data = []
    address_data = []
    admin_data = []

    # New list of tags for enrichment, targeting District and lower admin levels
    ADMIN_FILTERS = ["addr:district", "addr:city", "addr:postcode", "admin_level"]

    for element in elements:
        element_type = element.get("type")
        tags = element.get("tags", {})

        # A. Extract Building Polygons (no change)
        if element_type in ("way", "relation") and tags.get("building"):
            # ... (logic to create polygon and append to building_data) ...
            if "geometry" in element:
                coords = [(n["lon"], n["lat"]) for n in element["geometry"]]
                if len(coords) >= 3:
                    try:
                        polygon = Polygon(coords)
                        building_data.append(
                            {
                                "osm_id": element["id"],
                                "geometry": polygon,
                            }
                        )
                    except Exception:
                        pass

        # B. Extract Address Points (Nodes) - ADD addr:district
        if element_type == "node" and tags.get("addr:housenumber"):
            lat = element.get("lat")
            lon = element.get("lon")
            if lat is not None and lon is not None:
                address_data.append(
                    {
                        "addr_osm_id": element["id"],
                        "geometry": Point(lon, lat),
                        "addr_housenumber": tags.get("addr:housenumber"),
                        "addr_street": tags.get("addr:street"),
                        "addr_postcode": tags.get("addr:postcode"),
                        "addr_city": tags.get("addr:city"),
                        # NEW: Include addr:district if present on the node
                        "addr_district": tags.get("addr:district"),
                    }
                )

        # C. Extract Administrative Areas (Ways/Relations) - ADD admin_district
        if element_type in ("way", "relation") and any(
            tag in tags for tag in ADMIN_FILTERS
        ):
            if "geometry" in element:
                coords = [(n["lon"], n["lat"]) for n in element["geometry"]]
                if len(coords) >= 3:
                    try:
                        polygon = Polygon(coords)
                        admin_data.append(
                            {
                                "admin_city": tags.get("addr:city"),
                                "admin_postcode": tags.get("addr:postcode"),
                                # NEW: Extract District info from administrative polygons
                                "admin_district": tags.get("addr:district")
                                or tags.get("name"),
                                "geometry": polygon,
                            }
                        )
                    except Exception:
                        pass

    # Create GeoDataFrames
    # ... (gdf_buildings, gdf_addresses, gdf_admin creation) ...
    gdf_buildings = gpd.GeoDataFrame(building_data, crs="EPSG:4326")
    gdf_addresses = gpd.GeoDataFrame(address_data, crs="EPSG:4326")
    gdf_admin = gpd.GeoDataFrame(admin_data, crs="EPSG:4326")

    return gdf_buildings, gdf_addresses, gdf_admin


# --- Function 2: Perform Spatial Joins ---


def perform_spatial_join(
    gdf_buildings: gpd.GeoDataFrame,
    gdf_addresses: gpd.GeoDataFrame,
    gdf_admin: gpd.GeoDataFrame,
):

    # 1. Join Address Nodes to Building Polygons (no change, just ensuring index_right fix)
    joined_data_buildings = gpd.sjoin(
        left_df=gdf_addresses,
        right_df=gdf_buildings[["osm_id", "geometry"]],
        how="left",
        predicate="within",
    ).rename(columns={"osm_id": "building_osm_id"})

    if "index_right" in joined_data_buildings.columns:
        joined_data_buildings = joined_data_buildings.drop(columns=["index_right"])

    # 2. Join Addresses to Administrative Polygons (Spatial Inheritance)
    # Inherit District, City, and Postcode
    address_with_admin = gpd.sjoin(
        left_df=joined_data_buildings,
        right_df=gdf_admin[
            ["admin_city", "admin_postcode", "admin_district", "geometry"]
        ],  # ADDED admin_district
        how="left",
        predicate="within",
    )

    # 3. Data Consolidation (Filling the Gaps)

    # NEW: Fill missing 'addr_district' using the inherited 'admin_district' tag
    address_with_admin["addr_district"] = address_with_admin["addr_district"].fillna(
        address_with_admin["admin_district"]
    )

    # Fill missing 'addr_city' using the inherited 'admin_city' tag
    address_with_admin["addr_city"] = address_with_admin["addr_city"].fillna(
        address_with_admin["admin_city"]
    )

    # Fill missing 'addr_postcode' using the inherited 'admin_postcode' tag
    address_with_admin["addr_postcode"] = address_with_admin["addr_postcode"].fillna(
        address_with_admin["admin_postcode"]
    )

    # 4. Final Output Formatting - ADD addr_district
    final_output = address_with_admin[
        [
            "addr_osm_id",
            "building_osm_id",
            "addr_housenumber",
            "addr_street",
            "addr_district",  # NEW
            "addr_city",
            "addr_postcode",
            "geometry",
        ]
    ].copy()

    final_output["lon"] = final_output.geometry.x
    final_output["lat"] = final_output.geometry.y

    # Safely drop final temporary columns
    columns_to_drop = ["geometry"]
    if "index_right" in final_output.columns:
        columns_to_drop.append("index_right")

    return final_output.drop(columns=columns_to_drop, errors="ignore")


# --- Main Execution with Argparse ---


def main():
    p = argparse.ArgumentParser(
        description="Performs a spatial join on raw OSM data (buildings/addresses) to enrich address tags."
    )
    p.add_argument(
        "--input-json",
        type=str,
        default="data/address_data.json",
        help="Path to the input JSON file containing raw OSM elements (output from Overpass query).",
    )
    p.add_argument(
        "--output-csv",
        type=str,
        default="data/final_joined_addresses.csv",
        help="Path for the output CSV file containing the joined and enriched addresses.",
    )
    args = p.parse_args()

    input_path = args.input_json
    output_path = args.output_csv

    print(f"Loading raw OSM data from {input_path}...")

    # Load Data
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file not found at {input_path}.")
        return 1
    except json.JSONDecodeError:
        print(f"Error: Input file {input_path} is not a valid JSON file.")
        return 1

    elements = raw_data.get("elements", [])
    print(f"Loaded {len(elements)} elements.")

    # 1. Process and separate data
    gdf_buildings, gdf_addresses, gdf_admin = process_osm_elements(elements)

    print("-" * 40)
    print(f"Found {len(gdf_buildings)} building polygons.")
    print(f"Found {len(gdf_addresses)} house-level address nodes.")
    print(f"Found {len(gdf_admin)} administrative boundaries for enrichment.")
    print("-" * 40)

    if gdf_addresses.empty:
        print("No house-level address nodes found. Aborting spatial join.")
        return 0

    # 2. Perform Spatial Join
    final_addresses = perform_spatial_join(gdf_buildings, gdf_addresses, gdf_admin)
    print(f"Successfully joined and enriched {len(final_addresses)} address records.")

    # 3. Export Results
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    final_addresses.to_csv(output_path, index=False)
    print(f"\nFinal address data saved to {output_path}")
    print("\n--- Sample Output ---\n")
    print(final_addresses.head())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
