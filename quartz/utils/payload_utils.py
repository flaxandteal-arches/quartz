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


def extract_gps_features(locations: list, lat_key: str, lon_key: str) -> list:
    """Convert a list of location dicts to GeoJSON Point features."""
    features = []
    for loc in locations:
        if loc.get("location_type") != "GPS":
            continue

        lat = loc.get(lat_key)
        lon = loc.get(lon_key)

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
    try:
        uuid.UUID(list_name)
        list_pk = list_name
    except ValueError:
        list_pk = str(List.objects.get(name=list_name).pk)

    config = {"controlledList": list_pk}

    return reference.transform_value_for_tile(value, **config)


def make_or_update_tiles(
    nodegroup_id: str,
    new_data: list[dict] | dict,
    resource_instance_ref: str,
    parent_tile_id: str = None,
) -> list:
    """
    If existing_tiles is empty, create a new tile with the new_data.
    If existing_tiles has one tile, update its data with new_data.
    If existing_tiles has multiple tiles, log a warning and update the first tile.
    """

    tiles = []

    if isinstance(new_data, dict):
        new_data = [new_data]

    existing_tiles = Tile.objects.filter(
        resourceinstance_id=resource_instance_ref,
        nodegroup_id=nodegroup_id,
    )

    if not existing_tiles.exists():
        for item in new_data:
            tiles.append(make_tile(nodegroup_id, item, parent_tile_id))
        return tiles
    else:
        keys_to_replace = set(new_data[0].keys())

        for tile in existing_tiles:
            for key in keys_to_replace:
                tile.data.pop(key, None)

        for idx, item in enumerate(new_data):
            if idx < len(existing_tiles):
                existing_tiles[idx].data = {**existing_tiles[idx].data, **item}
                tiles.append(existing_tiles[idx])
            else:
                tiles.append(make_tile(nodegroup_id, item, parent_tile_id))

        return tiles
        # return update_tiles(existing_tiles, new_data, nodegroup_id, parent_tile_id)


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


def get_or_create_person_resource_from_name(name: str, user) -> str:
    """
    Get or create a Person resource with the given name, and return its resourceinstanceid.
    This is used for mapping the 'modifiedby' field from the payload to a Person resource in Arches.
    """
    from arches.app.models.resource import Resource
    from arches.app.models.tile import Tile
    from django.db.models import Q

    resource_filter = Q(nodegroup_id="4110f741-1a44-11e9-885e-000d3ab1e588") & Q(
        **{"data__5f8ded26-7ef9-11ea-8e29-f875a44e0e11__en__value": name}
    )

    existing = Tile.objects.filter(resource_filter).first()

    if existing:
        return str(existing.resourceinstanceid)

    return "not found"

    # new_resource = Resource()
    # new_resource.save(user=user)
    # name_tile = Tile(
    #     {
    #         "tileid": uuid.uuid4(),
    #         "nodegroup_id": "4110f741-1a44-11e9-885e-000d3ab1e588",
    #         "data": {"dpp_person_name": i18n_string(name)},
    #     }
    # )
    # name_tile.save()
    # new_resource.tiles.add(name_tile)
    # new_resource.save()
    # return str(new_resource.resourceinstanceid)
