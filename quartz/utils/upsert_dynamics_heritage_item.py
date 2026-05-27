import logging

from arches.app.models import models
from arches.app.models.resource import Resource
from arches.app.models.tile import Tile

from arches_resource_version_manager.lifecycle import (
    archive_copy_of_current_draft,
    finalize_draft,
    register_new_draft,
)
from arches_resource_version_manager.models import VersionedResource

from .payload_utils import (
    extract_gps_features,
    i18n_string,
    make_tile,
    parse_date,
    parse_reference_node,
    parse_resource_instance_id,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Heritage Item graph and node constants
# ---------------------------------------------------------------------------

HERITAGE_ITEM_GRAPH_ID = "076f9381-7b00-11e9-8d6b-80000b44d1d9"

# Names nodegroup  (repeatable — one tile per name entry)
NAMES_NODEGROUP = "676d47f9-9c1c-11ea-9aa0-f875a44e0e11"
NODE_NAME = "676d47ff-9c1c-11ea-b07f-f875a44e0e11"  # string
NODE_NAME_TYPE = "676d47fe-9c1c-11ea-aa28-f875a44e0e11"  # reference
NODE_NAME_USE_TYPE = "676d47fc-9c1c-11ea-b5b0-f875a44e0e11"  # reference
PRIMARY_NAME_USE_TYPE = {
    "labels": [
        {
            "id": "d49999ca-d28c-412b-8ece-35984980b836",
            "language_id": "en",
            "list_item_id": "d4e3d550-6e2d-4734-88d4-3e781118048d",
            "value": "Primary",
            "valuetype_id": "prefLabel",
        }
    ],
    "list_id": "1e4df896-992b-475e-bb5a-78817d3066d7",
    "uri": "d4e3d550-6e2d-4734-88d4-3e781118048d",
}
ALTERNATIVE_NAME_USE_TYPE = {
    "labels": [
        {
            "id": "7d308b8d-a1b7-433c-a172-d044796fd585",
            "language_id": "en",
            "list_item_id": "f2a2710a-5a81-435a-9f2f-4eeddcdcd4af",
            "value": "Alternative",
            "valuetype_id": "prefLabel",
        }
    ],
    "list_id": "1e4df896-992b-475e-bb5a-78817d3066d7",
    "uri": "f2a2710a-5a81-435a-9f2f-4eeddcdcd4af",
}

# Designation and Protection Assignment nodegroup  (repeatable — one tile per designation/protection entry)
DESIGNATION_NODEGROUP = "6af2a0cb-efc5-11eb-8436-a87eeabdefba"
DESIGNATION_OR_PROTECTION_TYPE = "6af2a0ce-efc5-11eb-88d1-a87eeabdefba"  # TODO
DESIGNATION_START_DATE = "6af2b69b-efc5-11eb-8d5a-a87eeabdefba"
DESIGNATION_END_DATE = "6af2b6a0-efc5-11eb-985a-a87eeabdefba"

# System Reference Numbers nodegroup  (repeatable)
SYSTEM_REF_NODEGROUP = "325a2f2f-efe4-11eb-9b0c-a87eeabdefba"
NODE_PRIMARY_REF_NUM = "325a2f33-efe4-11eb-b0bb-a87eeabdefba"  # number

# version information nodegroup (one tile — not repeatable)
VERSIONING_NODEGROUP = "03d5eb66-d748-57cc-8390-5788078696d7"
VERSION_NUMBER = "4b1880ea-33a8-50ea-aa1d-455c2ed95787"  # string
WORKING_COPY = "0f5a7e18-c9a0-52ea-81f1-9a493b4f1f23"  # reference to working draft

# Location Data nodegroup  (container — cleared on upsert along with child nodegroups)
LOCATION_DATA_NODEGROUP = "87d39b2e-f44f-11eb-9a4a-a87eeabdefba"

# Addresses nodegroup  (repeatable — one tile per address; part of Location Data in UI)
ADDRESSES_NODEGROUP = "87d39b25-f44f-11eb-95e5-a87eeabdefba"
NODE_FULL_ADDRESS = "87d39b36-f44f-11eb-a905-a87eeabdefba"  # string

# Geometry nodegroup  (one tile — all GPS points merged into one FeatureCollection)
GEOMETRY_NODEGROUP = "87d3872b-f44f-11eb-bd0c-a87eeabdefba"
NODE_GEOSPATIAL_COORDS = (
    "87d3d7dc-f44f-11eb-bee9-a87eeabdefba"  # geojson-feature-collection
)


AREA_ASSIGNMENT_NODEGROUP = "87d39b22-f44f-11eb-887e-a87eeabdefba"
NODE_AREA_REFERENCE_VALUE = "87d3c3fc-f44f-11eb-beff-a87eeabdefba"  # dpp_plan

LOT_ON_PLAN_NODEGROUP = "6a19facf-8f47-54a2-84b8-d0173db7eaa3"
NODE_LOT = "5717a450-e62b-5dfa-857a-c42e7791a6e4"  # dpp_lot

# Descriptions nodegroup  (repeatable — one tile per description entry)
# DESCRIPTIONS_NODEGROUP = "ba342e69-b554-11ea-a027-f875a44e0e11"
# NODE_DESCRIPTION = "ba345577-b554-11ea-a9ee-f875a44e0e11"  # string
# NODE_DESCRIPTION_TYPE = "ba34557b-b554-11ea-ab95-f875a44e0e11"  # reference

# External Cross References nodegroup  (repeatable — one tile per lot/plan)
# EXTERNAL_XREF_NODEGROUP = "f17f6581-efc7-11eb-b09f-a87eeabdefba"
# NODE_EXTERNAL_XREF = "f17f6584-efc7-11eb-81f1-a87eeabdefba"  # string
# NODE_EXTERNAL_XREF_SOURCE = "f17f658a-efc7-11eb-a216-a87eeabdefba"  # reference

# Nodegroups whose tiles are fully replaced on each sync.
# Includes Location Data and all its UI child nodegroups (Addresses, Geometry, etc.).
_STATUTORY_NODEGROUPS = {
    NAMES_NODEGROUP,
    SYSTEM_REF_NODEGROUP,
    DESIGNATION_NODEGROUP,
    # LOCATION_DATA_NODEGROUP,
    ADDRESSES_NODEGROUP,
    GEOMETRY_NODEGROUP,
    AREA_ASSIGNMENT_NODEGROUP,
    LOT_ON_PLAN_NODEGROUP,
    # DESCRIPTIONS_NODEGROUP,
    # EXTERNAL_XREF_NODEGROUP,
}

_MANAGED_NODEGROUPS = _STATUTORY_NODEGROUPS | {VERSIONING_NODEGROUP}

FINAL_STATUSES = {"final"}


def process_heritage_item(payload: dict, user) -> tuple:
    """
    Implements the Payload API logical data flow:

    New item (6000 number not in VersionedResource):
        - Create a Draft Resource from the payload.
        - Add a Draft entry to VersionedResource.

    Existing item (6000 number found in VersionedResource):
        - Look up the latest Draft resource.
        - Clone the Draft for archival before mutating it.
        - Update the Draft resource with the incoming payload data.
        - If the payload is Final:
        - Archive the current Final resource, if any.
        - Clone the updated Draft as the new Final resource.
        - Add a Final entry to VersionedResource.

    Returns (resource, created_bool).
    """
    heritage_id_number = payload.get("dpp_heritageidnumber")
    version_from_payload = payload.get("dpp_version")

    if not heritage_id_number:
        raise ValueError("Missing required field: dpp_heritageidnumber")

    is_final = _is_final_payload(payload)

    # ------------------------------------------------------------------
    # Is the 6000 number in the Resource Version table?
    # ------------------------------------------------------------------
    current_draft_version = VersionedResource.objects.get_current_draft(
        heritage_id_number
    )

    next_major, next_minor = _next_version(
        is_final,
        current_draft_version.major_version if current_draft_version else None,
        current_draft_version.minor_version if current_draft_version else None,
        version_from_payload,
    )

    if not current_draft_version:
        # New item: create a Draft Resource and record it in the version table.
        # TODO - should we be checking if a resource instance already exists with the incoming 6000 number?
        resource = Resource()
        resource.graph_id = HERITAGE_ITEM_GRAPH_ID
        resource.tiles = _build_managed_tiles(
            payload, next_major, next_minor, resource.pk
        )
        resource.save(user=user)

        register_new_draft(
            resource, heritage_id_number, next_major, next_minor, payload
        )

        if is_final:
            finalize_draft(heritage_id_number, user, next_major, next_minor, payload)

        return resource, True, f"{next_major}.{next_minor}"

    # ------------------------------------------------------------------
    # Existing item: archive the current Draft and get back the resource.
    # ------------------------------------------------------------------
    archive_copy_of_current_draft(heritage_id_number, user)

    current_draft_version.metadata = payload
    current_draft_version.major_version = next_major
    current_draft_version.minor_version = next_minor
    current_draft_version.save()

    current_draft_resource = models.Resource.objects.get(pk=current_draft_version.pk)

    # Update the Draft resource with data from the incoming payload.
    models.TileModel.objects.filter(
        resourceinstance_id=current_draft_resource.pk,
        nodegroup_id__in=_MANAGED_NODEGROUPS,
    ).delete()

    current_draft_resource.tiles = _build_managed_tiles(
        payload,
        next_major,
        next_minor,
        current_draft_resource.pk,
    )
    current_draft_resource.save()

    if is_final:
        finalize_draft(heritage_id_number, user, next_major, next_minor, payload)

    return current_draft_resource, False, f"{next_major}.{next_minor}"


def _next_version(
    is_final: bool,
    current_major: int,
    current_minor: int,
    version_from_payload,
) -> tuple[int, int]:
    if is_final or (current_major is None and current_minor is None):
        return int(version_from_payload), 0
    return current_major, current_minor + 1


def _is_final_payload(payload: dict) -> bool:
    return (payload.get("status") or "").lower() in FINAL_STATUSES


def _build_managed_tiles(
    payload: dict,
    major_version: str | int,
    minor_version: str | int,
    resource_instance_ref: str,
) -> list:
    return (
        _build_system_ref_tiles(payload)
        + _build_designation_tiles(payload)
        + _build_name_tiles(payload)
        + _build_location_tiles(payload, resource_instance_ref)
        + _build_version_tile(major_version, minor_version, resource_instance_ref)
    )


def _build_version_tile(
    major_version: str | int, minor_version: str | int, resource_instance_ref: str
) -> list:
    return [
        make_tile(
            VERSIONING_NODEGROUP,
            {
                VERSION_NUMBER: i18n_string(f"{major_version}.{minor_version}"),
                WORKING_COPY: parse_resource_instance_id(resource_instance_ref),
            },
        )
    ]


def _build_system_ref_tiles(payload: dict) -> list:
    heritage_id = payload.get("dpp_heritageidnumber")
    if not heritage_id:
        return []
    return [make_tile(SYSTEM_REF_NODEGROUP, {NODE_PRIMARY_REF_NUM: int(heritage_id)})]


def _build_designation_tiles(payload: dict) -> list:
    designation = payload.get("dpp_designationprotection")
    designation_start_date = payload.get("dpp_dateenteredregister")
    designation_end_date = payload.get("dpp_dateremovedfromregister")
    if not (designation or designation_start_date or designation_end_date):
        return []
    return [
        make_tile(
            DESIGNATION_NODEGROUP,
            {
                # TODO - map DESIGNATION_OR_PROTECTION_TYPE to a reference node
                # DESIGNATION_OR_PROTECTION_TYPE: i18n_string(designation),
                DESIGNATION_START_DATE: parse_date(designation_start_date),
                DESIGNATION_END_DATE: parse_date(designation_end_date),
            },
        )
    ]


def _build_name_tiles(payload: dict) -> list:
    tiles = []

    primary_name = payload.get("dpp_name")
    if primary_name:
        tiles.append(
            make_tile(
                NAMES_NODEGROUP,
                {
                    NODE_NAME: i18n_string(primary_name),
                    NODE_NAME_USE_TYPE: [PRIMARY_NAME_USE_TYPE],
                },
                sortorder=0,
            )
        )

    # The alternative names field sometimes concatenates multiple names with " | ".
    for alt in payload.get("alternative_names", []):
        alt_name = alt.get("dpp_name")
        if alt_name:
            for index, part in enumerate(alt_name.split(" | ")):
                part = part.strip()
                if part:
                    tiles.append(
                        make_tile(
                            NAMES_NODEGROUP,
                            {
                                NODE_NAME: i18n_string(part),
                                NODE_NAME_USE_TYPE: [ALTERNATIVE_NAME_USE_TYPE],
                            },
                            sortorder=index + 1,
                        )
                    )

    return tiles


def _build_location_tiles(payload: dict, resource_instance_ref: str) -> list:

    try:
        location_data_tile = Tile.objects.get(
            resourceinstance_id=resource_instance_ref,
            nodegroup_id=LOCATION_DATA_NODEGROUP,
        )
    except Tile.DoesNotExist:
        location_data_tile = make_tile(LOCATION_DATA_NODEGROUP, {})

    tiles = []
    tiles.append(location_data_tile)

    for loc in payload.get("Locations", []):
        if loc.get("location_type") == "Address":
            address = loc.get("cdm_name")
            if address:
                tiles.append(
                    make_tile(
                        ADDRESSES_NODEGROUP,
                        {NODE_FULL_ADDRESS: i18n_string(address)},
                        parent_tile_id=location_data_tile.tileid,
                    )
                )

        if loc.get("location_type") == "dpp_lot dpp_plan":
            lot = loc.get("dpp_lot")
            plan = loc.get("dpp_plan")
            if plan:
                area_assignment_tile = make_tile(
                    AREA_ASSIGNMENT_NODEGROUP,
                    {NODE_AREA_REFERENCE_VALUE: i18n_string(plan)},
                    parent_tile_id=location_data_tile.tileid,
                )
            else:
                area_assignment_tile = make_tile(
                    AREA_ASSIGNMENT_NODEGROUP,
                    {},
                    parent_tile_id=location_data_tile.tileid,
                )
            tiles.append(area_assignment_tile)

            if lot:
                tiles.append(
                    make_tile(
                        LOT_ON_PLAN_NODEGROUP,
                        {NODE_LOT: i18n_string(lot)},
                        parent_tile_id=area_assignment_tile.tileid,
                    )
                )

    gps_features = extract_gps_features(payload.get("Locations", []))
    if gps_features:
        tiles.append(
            make_tile(
                GEOMETRY_NODEGROUP,
                {
                    NODE_GEOSPATIAL_COORDS: {
                        "type": "FeatureCollection",
                        "features": gps_features,
                    }
                },
                parent_tile_id=location_data_tile.tileid,
            )
        )

    return tiles
