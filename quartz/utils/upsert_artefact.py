import logging
import uuid

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
    get_or_create_person_resource_from_name,
    get_or_create_digital_object_resource_from_name,
    i18n_string,
    make_tile,
    make_or_update_tiles as payload_make_or_update_tiles,
    parse_date,
    parse_reference_node,
    parse_resource_instance_id,
    has_value,
    has_any_value,
)

from .versioned_resource_utils import calculate_next_version

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Artefact graph and node constants
# ---------------------------------------------------------------------------

ARTEFACT_GRAPH_ID = "343cc20c-2c5a-11e8-90fa-0242ac120005"

# System Reference Numbers nodegroup  (one tile — not repeatable)
SYSTEM_REF_NODEGROUP = "dd800bc9-b494-11ea-9af8-f875a44e0e11"
NODE_PRIMARY_REF_NUM = "dd8032af-b494-11ea-8110-f875a44e0e11"  # number
NODE_LEGACY_ID = "dd8032b1-b494-11ea-a183-f875a44e0e11"  # string

# Version information nodegroup  (one tile — not repeatable)
VERSIONING_NODEGROUP = "07028e38-c27c-572f-8be5-e37ec837ad4f"
VERSION_NUMBER = "ddaac2c0-65f5-52ed-a843-43de724f9d01"  # string

DEACTIVATION_REASON_NODEGROUP = "7def03f0-3bf7-52dc-b226-76b3d00bc8a2"
NODE_DEACTIVATION_REASON = "7def03f0-3bf7-52dc-b226-76b3d00bc8a2"  # reference
DEACTIVATION_REASON_LIST_NAME = "Deactivation Reason"

# Artefact Names nodegroup  (repeatable — one tile per name)
ARTEFACT_NAMES_NODEGROUP = "5b0dfb23-7fe2-11ea-bf70-f875a44e0e11"
NODE_ARTEFACT_NAME = "5b0dfb27-7fe2-11ea-8ac9-f875a44e0e11"  # string

# External Cross References nodegroup  (repeatable)
EXTERNAL_CROSS_REFS_NODEGROUP = "4844c742-eec7-11eb-84e6-a87eeabdefba"
NODE_EXTERNAL_CROSS_REF = "4844c745-eec7-11eb-9089-a87eeabdefba"  # string

# Descriptions nodegroup  (repeatable — one tile per description)
DESCRIPTIONS_NODEGROUP = "c30977ad-991e-11ea-9368-f875a44e0e11"
NODE_DESCRIPTION = "c30977b0-991e-11ea-ba04-f875a44e0e11"  # string
NODE_DESCRIPTION_TYPE = "c30977b1-991e-11ea-b259-f875a44e0e11"  # reference
DESCRIPTION_TYPE_LIST_NAME = "Description Roles"

# Important Source of Information nodegroup  (one tile)
IMPORTANT_SOURCE_NODEGROUP = "88ace5fb-927a-57b5-9aba-a63346e4e573"
NODE_IMPORTANT_SOURCE = "88ace5fb-927a-57b5-9aba-a63346e4e573"  # reference
IMPORTANT_SOURCE_LIST_NAME = "Important Source of Information"

# Permission to Interfere nodegroup  (one tile)
PERMISSION_NODEGROUP = "6452f897-1b16-5fc5-9fcd-e6d43f48ce49"
NODE_PERMISSION = "6452f897-1b16-5fc5-9fcd-e6d43f48ce49"  # reference
PERMISSION_LIST_NAME = "Permission to Interfere Previously Granted"

# Production nodegroup  (contains artefact_type — repeatable)
PRODUCTION_NODEGROUP = "99cfca45-381d-11e8-968a-dca90488358a"
NODE_ARTEFACT_TYPE = "546b1630-3ba4-11eb-9030-f875a44e0e11"  # reference
NODE_ASSOCIATED_PERSON = (
    "dde0f338-bd41-11ea-afd6-f875a44e0e11"  # resource instance list
)
ARTEFACT_TYPE_LIST_NAME = "Artefact Types AD"

# Discovery nodegroup  (contains discovery_method)
DISCOVERY_NODEGROUP = "28c9f728-2c5f-11e8-90fa-0242ac120005"
NODE_DISCOVERY_METHOD = "28ca0042-2c5f-11e8-90fa-0242ac120005"  # reference
NODE_ARCHAEOLOGY_DISCOVERY_TYPE = "e1fd4c86-30e8-5f1b-b605-9452a5ded960"
DISCOVERY_METHOD_LIST_NAME = "Contexts"
ARCHAEOLOGY_DISCOVERY_TYPE_LIST_NAME = "Archaeological Discovery Type"

# Condition Assessment nodegroup  (contains start and end dates)
CONDITION_ASSESSMENT_NODEGROUP = "0b2fcd21-381d-11e8-b7d4-dca90488358a"
NODE_DATE_OF_ASSESSMENT_START = "0b2fdbc7-381d-11e8-ac6d-dca90488358a"  # date
NODE_DATE_OF_ASSESSMENT_END = "e75b6d90-863b-11ea-90c0-f875a44e0e11"  # date

# Archaeology Status nodegroup  (one tile)
ARCHAEOLOGY_STATUS_NODEGROUP = "6d658d05-857e-5aa3-b265-314f89e1804e"
NODE_ARCHAEOLOGY_STATUS = "6d658d05-857e-5aa3-b265-314f89e1804e"  # reference
ARCHAEOLOGY_STATUS_LIST_NAME = "Archaeology Status"

# Associated Monuments, Areas and Artefacts nodegroup  (one tile — resource-instance-list)
ASSOCIATED_MONUMENTS_NODEGROUP = "f019f44a-8639-11ea-988b-f875a44e0e11"
NODE_MONUMENT_AREA_OR_ARTEFACT = (
    "b0a53628-b539-11ea-8b11-f875a44e0e11"  # resource-instance-list
)

# Digital Files nodegroup  (one tile — resource-instance-list)
DIGITAL_OBJECT_NODEGROUP = "1cfbc009-860f-11ea-a7a6-f875a44e0e11"
NODE_DIGITAL_OBJECT = "1cfbc009-860f-11ea-a7a6-f875a44e0e11"  # resource-instance-list

# Location Data nodegroup  (container — cleared on upsert along with child nodegroups)
LOCATION_DATA_NODEGROUP = "f7cc62b1-f447-11eb-bde0-a87eeabdefba"

# Addresses nodegroup  (repeatable — one tile per address; part of Location Data in UI)
ADDRESSES_NODEGROUP = "f7cc62a8-f447-11eb-9fae-a87eeabdefba"
NODE_FULL_ADDRESS = "f7cc8c72-f447-11eb-a7f5-a87eeabdefba"  # string
NODE_POSTCODE = "f7ccef67-f447-11eb-a0eb-a87eeabdefba"  # string
NODE_BUILDING_NUMBER = "f7cc8c85-f447-11eb-b1c8-a87eeabdefba"
NODE_STREET_NAME = "f7cca076-f447-11eb-8e8e-a87eeabdefba"
NODE_SUBURBS = "0a2dfbb1-c230-4c95-bad6-1c264d90b6e9"
NODE_COUNTY = "f7ccef76-f447-11eb-ae38-a87eeabdefba"
NODE_LGA = "a0294ac1-7d0f-44fc-ba9e-08db1dc79e0b"
LGA_LIST_NAME = "LGAs"
SUBURB_LIST_NAME = "Suburbs"

# Geometry nodegroup  (one tile — all GPS points merged into one FeatureCollection)
GEOMETRY_NODEGROUP = "f7cc629f-f447-11eb-b2d3-a87eeabdefba"
NODE_GEOSPATIAL_COORDS = (
    "f7ccc8b9-f447-11eb-9cb1-a87eeabdefba"  # geojson-feature-collection
)
NODE_FEATURE_SHAPE = "f7cc8c75-f447-11eb-953a-a87eeabdefba"
FEATURE_SHAPE_LIST_NAME = "Feature Types"

# Coordinate System nodegroup  (coordinate_system_value — child of location_data)
COORDINATE_SYSTEM_NODEGROUP = "f7cca095-f447-11eb-b171-a87eeabdefba"
NODE_COORDINATE_SYSTEM = "f7cc8c78-f447-11eb-9fc1-a87eeabdefba"  # reference
COORDINATE_SYSTEM_LIST_NAME = "SCS"

# Capture Scale nodegroup  (one tile per location — child of location_data)
CAPTURE_SCALE_NODEGROUP = "f7ccef5f-f447-11eb-8b98-a87eeabdefba"
NODE_CAPTURE_SCALE = "f7ccef5f-f447-11eb-8b98-a87eeabdefba"  # reference
CAPTURE_SCALE_LIST_NAME = "Point Sources"

# Spatial Accuracy Qualifier nodegroup  (one tile per location — child of location_data)
SPATIAL_ACCURACY_NODEGROUP = "f7cca099-f447-11eb-8a56-a87eeabdefba"
NODE_SPATIAL_ACCURACY = "f7cca099-f447-11eb-8a56-a87eeabdefba"  # reference
SPATIAL_ACCURACY_LIST_NAME = (
    "6afdfd0e-5c44-510f-bc75-dcca147cb4d1"  # "Spatial Accuracy Qualifiers"
)

SPATIAL_RECORD_UPDATE_NODEGROUP = "f7ccc8ae-f447-11eb-8d86-a87eeabdefba"
NODE_UPDATE_START_DATE = "f7ccc899-f447-11eb-8271-a87eeabdefba"

# Spatial Metadata Descriptions nodegroup  (repeatable — child of location_data)
SPATIAL_METADATA_DESCRIPTIONS_NODEGROUP = "f7ccef51-f447-11eb-8c32-a87eeabdefba"
NODE_SPATIAL_METADATA_NOTES = "f7ccef57-f447-11eb-9619-a87eeabdefba"  # string

LOT_ON_PLAN_NODEGROUP = "925d9a2b-b933-4436-af2f-9c7aaf2c742e"
NODE_LOT = "2ea01f80-4846-4293-9a01-748666814140"  # dpp_lot
NODE_PLAN = "67045457-12b1-4a71-9cae-276c5a5b2522"  # dpp_plan


FINAL_STATUSES = {"recorded"}


def _managed_nodegroup_ids() -> set[str]:
    return {
        value
        for name, value in globals().items()
        if name.endswith("_NODEGROUP") and isinstance(value, str) and value
    }


def _managed_node_ids() -> set[str]:
    return {
        value
        for name, value in globals().items()
        if name.startswith("NODE_") and isinstance(value, str) and value
    }


def _clear_managed_node_values(resource_instance_ref: str) -> None:
    """Clear managed node values from managed nodegroup tiles for a resource."""
    if not resource_instance_ref:
        return

    nodegroups = _managed_nodegroup_ids()
    node_ids = _managed_node_ids()
    if not nodegroups or not node_ids:
        return

    tiles = models.TileModel.objects.filter(
        resourceinstance_id=resource_instance_ref,
        nodegroup_id__in=nodegroups,
    )

    updated_tiles = []
    for tile in tiles:
        data = tile.data or {}
        had_changes = False
        for node_id in node_ids:
            if node_id in data:
                data.pop(node_id, None)
                had_changes = True

        if had_changes:
            tile.data = data
            updated_tiles.append(tile)

    if updated_tiles:
        models.TileModel.objects.bulk_update(updated_tiles, ["data"])


def _prefetch_managed_tiles_by_nodegroup(resource_instance_ref: str) -> dict[str, list]:
    """Fetch all managed nodegroup tiles once and index them by nodegroup ID."""
    nodegroups = _managed_nodegroup_ids()
    if not resource_instance_ref or not nodegroups:
        return {}

    tiles_by_nodegroup = {}
    tiles = Tile.objects.filter(
        resourceinstance_id=resource_instance_ref,
        nodegroup_id__in=nodegroups,
    ).order_by("sortorder")

    for tile in tiles:
        key = str(tile.nodegroup_id)
        tiles_by_nodegroup.setdefault(key, []).append(tile)

    return tiles_by_nodegroup


def _make_or_update_tiles_cached(
    nodegroup_id: str,
    new_data: list[dict] | dict,
    parent_tile_id: str = None,
    resource_instance_ref: str = None,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    """Use pre-fetched tiles when available, falling back to payload helper behavior."""
    if existing_tiles_by_nodegroup is None:
        return payload_make_or_update_tiles(
            nodegroup_id,
            new_data,
            parent_tile_id=parent_tile_id,
            resource_instance_ref=resource_instance_ref,
        )

    if isinstance(new_data, dict):
        new_data = [new_data]

    nodegroup_key = str(nodegroup_id)
    existing_tiles = existing_tiles_by_nodegroup.setdefault(nodegroup_key, [])

    if not existing_tiles:
        created_tiles = [make_tile(nodegroup_id, item, parent_tile_id) for item in new_data]
        existing_tiles.extend(created_tiles)
        return created_tiles

    keys_to_replace = set(new_data[0].keys()) if new_data else set()

    for tile in existing_tiles:
        tile.data = tile.data or {}
        for key in keys_to_replace:
            tile.data.pop(key, None)

    tiles = list(existing_tiles)

    for idx, item in enumerate(new_data):
        if idx < len(tiles):
            tiles[idx].data = {**(tiles[idx].data or {}), **item}
        else:
            new_tile = make_tile(nodegroup_id, item, parent_tile_id)
            tiles.append(new_tile)
            existing_tiles.append(new_tile)

    return tiles


def process_artefact(payload: dict, user) -> tuple:
    """
    Implements the Payload API logical data flow for Artefact resources:

    New item (discovery permit number not in VersionedResource):
        - Create a Draft Resource from the payload.
        - Add a Draft entry to VersionedResource.

    Existing item (discovery permit number found in VersionedResource):
        - Look up the latest Draft resource.
        - Clone the Draft for archival before mutating it.
        - Update the Draft resource with the incoming payload data.
        - If the payload is Final:
            - Archive the current Final resource, if any.
            - Clone the updated Draft as the new Final resource.
            - Add a Final entry to VersionedResource.

    Returns (resource, created_bool, version_string).
    """
    created = False
    discovery_permit_number = payload.get("dpp_permitnumber")
    version_from_payload = payload.get("dpp_version")

    if not discovery_permit_number:
        raise ValueError("Missing required field: dpp_permitnumber")

    is_final = _is_final_payload(payload)

    current_draft_version = VersionedResource.objects.get_current_draft(
        discovery_permit_number
    )

    next_major, next_minor = calculate_next_version(
        current_draft_version,
        is_final,
        version_from_payload,
    )
    transaction_id = uuid.uuid4()

    if not current_draft_version:
        resource = Resource()
        resource.graph_id = ARTEFACT_GRAPH_ID
        resource.tiles = _build_managed_tiles(payload, 0, 0, resource.pk)
        resource.save(user=user)

        current_draft_version = register_new_draft(
            resource, discovery_permit_number, 0, 0, payload
        )

        created = True

    archived_version = archive_copy_of_current_draft(
        discovery_permit_number, user, transaction_id
    )
    archived_resource = models.Resource.objects.get(pk=archived_version.pk)

    current_draft_version.metadata = payload
    current_draft_version.major_version = next_major
    current_draft_version.minor_version = next_minor
    current_draft_version.save()

    current_draft_resource = models.Resource.objects.get(pk=current_draft_version.pk)
    current_draft_resource.save_edit(
        transaction_id=transaction_id,
        user=user,
        edit_type="copy",
        note="Archived to",
        newvalue={
            "resourceinstanceid": str(archived_resource.pk),
            "descriptors": archived_resource.descriptors,
        },
    )

    _clear_managed_node_values(str(current_draft_resource.pk))
    existing_tiles_by_nodegroup = _prefetch_managed_tiles_by_nodegroup(
        str(current_draft_resource.pk)
    )

    current_draft_resource.tiles = _build_managed_tiles(
        payload,
        next_major,
        next_minor,
        current_draft_resource.pk,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )
    current_draft_resource.save()

    if is_final:
        finalize_draft(discovery_permit_number, user, next_major, next_minor, payload)

    return current_draft_resource, created, f"{next_major}.{next_minor}"


def increment_current_working_draft_version(
    resourceid: str, major_version: int, minor_version: int
):
    """Update or create the version information tile for the given resource instance."""
    current_draft_resource = Resource.objects.get(pk=resourceid)
    models.TileModel.objects.filter(
        resourceinstance_id=current_draft_resource.pk,
        nodegroup_id=VERSIONING_NODEGROUP,
    ).delete()
    current_draft_resource.tiles = _build_version_tile(
        major_version, minor_version, resourceid
    )
    return current_draft_resource


def _is_final_payload(payload: dict) -> bool:
    return (payload.get("dpp_archaeologystatus") or "").lower() in FINAL_STATUSES


def _build_managed_tiles(
    payload: dict,
    major_version: str | int,
    minor_version: str | int,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    discovery_tile = _get_or_build_discovery_tile(
        payload,
        resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )
    return (
        _build_system_ref_tile(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_version_tile(
            major_version,
            minor_version,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_deactivation_reason_tile(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_name_tiles(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_external_ref_tiles(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_description_tiles(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_important_source_tile(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_permission_tile(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_artefact_type_tile(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + [discovery_tile]
        + _build_condition_assessment_tile(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_archaeology_status_tile(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_associated_monuments_tile(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_digital_file_tile(
            payload,
            resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
        + _build_location_tiles(
            payload,
            resource_instance_ref,
            discovery_tile,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )
    )


def _build_version_tile(
    major_version: str | int,
    minor_version: str | int,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    return _make_or_update_tiles_cached(
        VERSIONING_NODEGROUP,
        {VERSION_NUMBER: i18n_string(f"{major_version}.{minor_version}")},
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )


def _build_system_ref_tile(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    permit_number = payload.get("dpp_permitnumber")
    legacy_id = payload.get("dpp_discoveryreferencenumber")
    if not has_value(permit_number) and not has_value(legacy_id):
        return []

    return _make_or_update_tiles_cached(
        SYSTEM_REF_NODEGROUP,
        {
            NODE_PRIMARY_REF_NUM: int(permit_number),
            NODE_LEGACY_ID: i18n_string(str(legacy_id)),
        },
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )


def _build_deactivation_reason_tile(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    reason = payload.get("dpp_deactivationreason")
    if not has_value(reason):
        return []
    return _make_or_update_tiles_cached(
        DEACTIVATION_REASON_NODEGROUP,
        {
            NODE_DEACTIVATION_REASON: parse_reference_node(
                reason, DEACTIVATION_REASON_LIST_NAME
            )
        },
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )



def _build_name_tiles(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    name = payload.get("dpp_discoveryname")
    if not has_value(name):
        return []
    return _make_or_update_tiles_cached(
        ARTEFACT_NAMES_NODEGROUP,
        {NODE_ARTEFACT_NAME: i18n_string(name)},
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )


def _build_external_ref_tiles(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    ref = payload.get("dpp_externalreferencenumber")
    if not has_value(ref):
        return []
    return _make_or_update_tiles_cached(
        EXTERNAL_CROSS_REFS_NODEGROUP,
        {NODE_EXTERNAL_CROSS_REF: i18n_string(str(ref))},
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )


def _build_description_tiles(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    descriptions = [
        ("dpp_response", "Response"),
        ("dpp_descriptionsummary", "Summary"),
    ]
    data = []
    for field, _type_label in descriptions:
        value = payload.get(field)
        if has_value(value):
            data.append(
                {
                    NODE_DESCRIPTION: i18n_string(value),
                    NODE_DESCRIPTION_TYPE: parse_reference_node(
                        _type_label, DESCRIPTION_TYPE_LIST_NAME
                    ),
                }
            )
    if data:
        return _make_or_update_tiles_cached(
            DESCRIPTIONS_NODEGROUP,
            data,
            resource_instance_ref=resource_instance_ref,
            existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
        )

    return []


def _build_important_source_tile(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    value = payload.get("dpp_importantsourceofinformation")
    if not has_value(value):
        return []
    return _make_or_update_tiles_cached(
        IMPORTANT_SOURCE_NODEGROUP,
        {
            NODE_IMPORTANT_SOURCE: parse_reference_node(
                value, IMPORTANT_SOURCE_LIST_NAME
            )
        },
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )


def _build_permission_tile(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    value = payload.get("dpp_permissiontointerferegranted")
    if not has_value(value):
        return []
    return _make_or_update_tiles_cached(
        PERMISSION_NODEGROUP,
        {NODE_PERMISSION: parse_reference_node(value, PERMISSION_LIST_NAME)},
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )


def _build_artefact_type_tile(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    value = payload.get("dpp_discoverysubtype")
    contact = payload.get("dpp_contact")
    applicant = payload.get("dpp_applicant")
    owner = payload.get("ownerid")
    if not has_any_value([value, contact, applicant, owner]):
        return []
    data = {
        NODE_ARTEFACT_TYPE: parse_reference_node(value, ARTEFACT_TYPE_LIST_NAME),
        NODE_ASSOCIATED_PERSON: [],
    }
    if has_value(payload.get("dpp_contact")):
        person_resource_id = get_or_create_person_resource_from_name(
            payload.get("dpp_contact"), "Correspondent"
        )
        data[NODE_ASSOCIATED_PERSON].extend(
            parse_resource_instance_id(person_resource_id)
        )
    if has_value(payload.get("dpp_applicant")):
        person_resource_id = get_or_create_person_resource_from_name(
            payload.get("dpp_applicant"), "Notifier"
        )
        data[NODE_ASSOCIATED_PERSON].extend(
            parse_resource_instance_id(person_resource_id)
        )
    if has_value(payload.get("ownerid")):
        person_resource_id = get_or_create_person_resource_from_name(
            payload.get("ownerid"), "Owner"
        )
        data[NODE_ASSOCIATED_PERSON].extend(
            parse_resource_instance_id(person_resource_id)
        )
    return _make_or_update_tiles_cached(
        PRODUCTION_NODEGROUP,
        data,
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )


def _get_or_build_discovery_tile(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> object:
    value = payload.get("dpp_context")
    discovery_type = payload.get("dpp_archaeologytype")
    tiles = _make_or_update_tiles_cached(
        DISCOVERY_NODEGROUP,
        {
            NODE_DISCOVERY_METHOD: parse_reference_node(
                value, DISCOVERY_METHOD_LIST_NAME
            ),
            NODE_ARCHAEOLOGY_DISCOVERY_TYPE: parse_reference_node(
                discovery_type,
                ARCHAEOLOGY_DISCOVERY_TYPE_LIST_NAME,
            ),
        },
        parent_tile_id=None,
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )

    return tiles[0]


def _build_condition_assessment_tile(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    start_date = payload.get("dpp_dateofdiscovery")
    end_date = payload.get("dpp_notificationdate")
    if not has_value(start_date) and not has_value(end_date):
        return []

    return _make_or_update_tiles_cached(
        CONDITION_ASSESSMENT_NODEGROUP,
        {
            NODE_DATE_OF_ASSESSMENT_START: parse_date(start_date),
            NODE_DATE_OF_ASSESSMENT_END: parse_date(end_date),
        },
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )


def _build_archaeology_status_tile(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    status = payload.get("dpp_archaeologystatus")
    if not has_value(status):
        return []
    return _make_or_update_tiles_cached(
        ARCHAEOLOGY_STATUS_NODEGROUP,
        {
            NODE_ARCHAEOLOGY_STATUS: parse_reference_node(
                status, ARCHAEOLOGY_STATUS_LIST_NAME
            )
        },
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )


def _build_associated_monuments_tile(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    items = payload.get("dpp_heritageitems", [])
    if not items:
        return []
    resource_instances = []
    for item in items:
        heritage_id_number = item.get("dpp_heritageidnumber")
        if heritage_id_number:
            # look up the heritage item from the 6000 number.
            # Get the current Draft version's resource instance ID to associate with.
            current_draft_version = VersionedResource.objects.get_current_draft(
                heritage_id_number
            )
            if current_draft_version:
                resource_instances.extend(
                    parse_resource_instance_id(
                        current_draft_version.resourceinstance_id
                    )
                )
    if not resource_instances:
        return []
    return _make_or_update_tiles_cached(
        ASSOCIATED_MONUMENTS_NODEGROUP,
        {NODE_MONUMENT_AREA_OR_ARTEFACT: resource_instances},
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )


def _build_digital_file_tile(
    payload: dict,
    resource_instance_ref: str,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    edocs_number = payload.get("dpp_edocsnumber")
    if not has_value(edocs_number):
        return []
    
    digital_object_resource_id = get_or_create_digital_object_resource_from_name(
        edocs_number
    )
    return _make_or_update_tiles_cached(
        DIGITAL_OBJECT_NODEGROUP,
        {
            NODE_DIGITAL_OBJECT: parse_resource_instance_id(
                digital_object_resource_id
            )
        },
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )


def _build_location_tiles(
    payload: dict,
    resource_instance_ref: str,
    discovery_tile: object,
    existing_tiles_by_nodegroup: dict[str, list] | None = None,
) -> list:
    tiles = []

    location_data_tile = _make_or_update_tiles_cached(
        LOCATION_DATA_NODEGROUP,
        {},
        parent_tile_id=discovery_tile.tileid,
        resource_instance_ref=resource_instance_ref,
        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
    )[0]
    tiles.append(location_data_tile)

    for loc in payload.get("locations", []):
        if loc.get("location_type") == "Address":
            address = loc.get("cdm_name")
            street_number = loc.get("dpp_numberfirst")
            street_name = loc.get("dpp_roadname")
            street_type = loc.get("dpp_roadtypecode")
            suburb = loc.get("dpp_localitynametext")
            state = loc.get("dpp_state")
            postcode = loc.get("dpp_postcode")
            lga = loc.get("dpp_localgovernmentareaname")

            street_name_full = (
                street_name + (" " + street_type if has_value(street_type) else "")
                if has_value(street_name)
                else None
            )

            data = {
                node: fn(val)
                for node, val, fn in [
                    (NODE_FULL_ADDRESS, address, i18n_string),
                    (NODE_LGA, lga, lambda v: parse_reference_node(v, LGA_LIST_NAME)),
                    (NODE_POSTCODE, postcode, i18n_string),
                    (NODE_BUILDING_NUMBER, street_number, i18n_string),
                    (NODE_STREET_NAME, street_name_full, i18n_string),
                    (
                        NODE_SUBURBS,
                        suburb,
                        lambda v: parse_reference_node(v, SUBURB_LIST_NAME),
                    ),
                    (NODE_COUNTY, state, i18n_string),
                ]
            }

            if data:
                tiles.extend(
                    _make_or_update_tiles_cached(
                        ADDRESSES_NODEGROUP,
                        data,
                        parent_tile_id=location_data_tile.tileid,
                        resource_instance_ref=resource_instance_ref,
                        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
                    )
                )

        if loc.get("location_type") == "Lot Plan":
            lot = loc.get("dpp_lot")
            plan = loc.get("dpp_plan")
            if has_value(lot) or has_value(plan):
                tiles.append(
                    make_tile(
                        LOT_ON_PLAN_NODEGROUP,
                        {
                            NODE_LOT: i18n_string(lot),
                            NODE_PLAN: i18n_string(plan),
                        },
                        parent_tile_id=location_data_tile.tileid,
                    )
                )

        if loc.get("location_type") == "GPS":
            gps_features = extract_gps_features(
                [loc], lat_key="dpp_latitude", lon_key="dpp_longitude"
            )
            feature_shape = loc.get("dpp_coordinatetype")
            geometry_tile = _make_or_update_tiles_cached(
                GEOMETRY_NODEGROUP,
                {
                    NODE_GEOSPATIAL_COORDS: {
                        "type": "FeatureCollection",
                        "features": gps_features,
                    },
                    NODE_FEATURE_SHAPE: parse_reference_node(feature_shape, FEATURE_SHAPE_LIST_NAME),
                },
                parent_tile_id=location_data_tile.tileid,
                resource_instance_ref=resource_instance_ref,
                existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
            )[0]
            tiles.append(geometry_tile)

            # capture_scale — locations.dpp_locationsource
            source = loc.get("dpp_locationsource")
            if has_value(source):
                tiles.extend(
                    _make_or_update_tiles_cached(
                        CAPTURE_SCALE_NODEGROUP,
                        {
                            NODE_CAPTURE_SCALE: parse_reference_node(
                                source, CAPTURE_SCALE_LIST_NAME
                            )
                        },
                        parent_tile_id=geometry_tile.tileid,
                        resource_instance_ref=resource_instance_ref,
                        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
                    )
                )

            # spatial_accuracy_qualifier — locations.dpp_locationaccuracy
            accuracy = loc.get("dpp_locationaccuracy")
            if has_value(accuracy):
                tiles.extend(
                    _make_or_update_tiles_cached(
                        SPATIAL_ACCURACY_NODEGROUP,
                        {
                            NODE_SPATIAL_ACCURACY: parse_reference_node(
                                accuracy, SPATIAL_ACCURACY_LIST_NAME
                            )
                        },
                        parent_tile_id=geometry_tile.tileid,
                        resource_instance_ref=resource_instance_ref,
                        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
                    )
                )

            # coordinate_system_value — locations.dpp_spatialcoordinatesystem
            coord_system = loc.get("dpp_spatialcoordinatesystem")
            if has_value(coord_system):
                tiles.extend(
                    _make_or_update_tiles_cached(
                        COORDINATE_SYSTEM_NODEGROUP,
                        {
                            NODE_COORDINATE_SYSTEM: parse_reference_node(
                                coord_system, COORDINATE_SYSTEM_LIST_NAME
                            )
                        },
                        parent_tile_id=geometry_tile.tileid,
                        resource_instance_ref=resource_instance_ref,
                        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
                    )
                )

            # spatial_record_update — locations.dpp_coordinatedate
            coord_date = loc.get("dpp_coordinatedate")
            if has_value(coord_date):
                tiles.append(
                    make_tile(
                        SPATIAL_RECORD_UPDATE_NODEGROUP,
                        {
                            NODE_UPDATE_START_DATE: parse_date(coord_date)
                        },
                        parent_tile_id=geometry_tile.tileid,
                    )
                )

            # spatial_metadata_notes — lat/lon/easting/northing combined into one string tile
            lat = loc.get("dpp_latitude")
            lon = loc.get("dpp_longitude")
            easting = loc.get("dpp_easting")
            northing = loc.get("dpp_northing")
            coordinate_description = loc.get("dpp_coordinatedescription")
            notes_parts = []
            if has_value(coordinate_description):
                notes_parts.append(f"{coordinate_description}")
            if has_value(lat):
                notes_parts.append(f"Latitude: {lat}")
            if has_value(lon):
                notes_parts.append(f"Longitude: {lon}")
            if has_value(easting):
                notes_parts.append(f"Easting: {easting}")
            if has_value(northing):
                notes_parts.append(f"Northing: {northing}")
            if has_value(loc.get("dpp_spatialcoordinatesystem")):
                notes_parts.append(
                    f"Coordinate System: {loc.get('dpp_spatialcoordinatesystem')}"
                )
            if notes_parts:
                tiles.extend(
                    _make_or_update_tiles_cached(
                        SPATIAL_METADATA_DESCRIPTIONS_NODEGROUP,
                        {
                            NODE_SPATIAL_METADATA_NOTES: i18n_string(
                                "<br>".join(notes_parts)
                            )
                        },
                        parent_tile_id=geometry_tile.tileid,
                        resource_instance_ref=resource_instance_ref,
                        existing_tiles_by_nodegroup=existing_tiles_by_nodegroup,
                    )
                )
                

    return tiles
