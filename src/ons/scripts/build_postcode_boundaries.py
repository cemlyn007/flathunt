import argparse
import json
import os
import scipy.spatial
import tqdm
import ons.pd

import ons.voronoi

if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser("Build Voronoi London Postcodes")
    argument_parser.add_argument(
        "--onspds", type=str, required=True, help="ONSPD file path"
    )
    argument_parser.add_argument(
        "--save",
        type=str,
        help="JSON file path",
        default=os.path.join("assets", "postcode_boundaries.json"),
    )
    arguments = argument_parser.parse_args()

    filepath = arguments.onspds
    save_filepath = arguments.save

    coordinate_postcodes_mapping = {}
    for postcode, latitude, longitude in tqdm.tqdm(
        ons.pd.read_london_active_postcode_centroids(filepath), desc="Reading ONSPD"
    ):
        ons.pd.assert_valid_postcode(postcode)
        coordinate_postcodes_mapping.setdefault((longitude, latitude), []).append(
            postcode
        )

    # Some postcodes have the same coordinates.
    unique_coordinates = list(set(coordinate_postcodes_mapping.keys()))

    voronoi = scipy.spatial.Voronoi(unique_coordinates)
    voronoi_face_edges = ons.voronoi.get_all_face_vertices(voronoi)

    polylines = [
        ons.voronoi.get_polylines(face_edges)
        for face_edges in tqdm.tqdm(voronoi_face_edges, desc="Converting to polylines")
    ]

    postcode_polylines = {
        postcode: polyline
        for coordinate, polyline in zip(unique_coordinates, polylines, strict=True)
        for postcode in coordinate_postcodes_mapping[coordinate]
    }
    with open(save_filepath, "w") as file:
        json.dump(postcode_polylines, file)
