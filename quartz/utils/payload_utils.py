import logging
import uuid
from datetime import datetime

from arches.app.datatypes.datatypes import DataTypeFactory
from arches.app.models.tile import Tile

from arches_controlled_lists.models import List

logger = logging.getLogger(__name__)


def i18n_string(value: str) -> dict:
    """Wrap a plain string in Arches 8 i18n format."""
    return {"en": {"value": value, "direction": "ltr"}}


def parse_date(value: str):
    """
    Convert a date string to YYYY-MM-DD (the format Arches date nodes expect).
    Accepts DD/MM/YYYY, YYYY-MM-DD, and ISO 8601 timestamps.
    Returns None if the value is blank or unparseable.
    """
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    logger.warning("Could not parse date value: %r", value)
    return None


def parse_resource_instance_id(value: str) -> object:
    return [
        {
            "resourceId": str(value),
            "ontologyProperty": "",
            "inverseOntologyProperty": "",
        }
    ]


def extract_gps_features(locations: list) -> list:
    """Convert a list of location dicts to GeoJSON Point features."""
    features = []
    for loc in locations:
        if loc.get("location_type") != "GPS":
            continue

        if "dpp_WGS84_lat" in loc and "dpp_WGS84_long" in loc:
            lat = loc.get("dpp_WGS84_lat")
            lon = loc.get("dpp_WGS84_lon")
        else:
            lat = loc.get("dpp_latitude")
            lon = loc.get("dpp_longitude")

        try:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(lon), float(lat)],  # GeoJSON: [lon, lat]
                    },
                    "properties": {},
                }
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Invalid GPS values lat=%r lon=%r: %s", lat, lon, exc)

    return features


def parse_reference_node(value: str, list_name: str) -> dict:
    """Convert a reference node value to the format Arches expects."""
    reference = DataTypeFactory().get_instance("reference")
    list_pk = str(List.objects.get(name=list_name).pk)
    config = {"controlledList": list_pk}

    return reference.transform_value_for_tile(value, **config)


def make_tile(
    nodegroup_id: str, data: dict, parent_tile_id: str = None, sortorder: int = 0
) -> Tile:
    return Tile(
        {
            "tileid": uuid.uuid4(),
            "nodegroup_id": nodegroup_id,
            "parenttile_id": parent_tile_id,
            "data": data,
            "sortorder": sortorder,
        }
    )


def update_tiles(tiles: list, data: dict) -> list:
    for tile in tiles:
        tile.data = {**tile.data, **data}
    return tiles


def has_value(value) -> bool:
    """Return True if the value is not None and not an empty string."""
    return value is not None and str(value).strip() != ""
