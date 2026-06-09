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
    i18n_string,
    make_tile,
    parse_date,
    parse_reference_node,
    parse_resource_instance_id,
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

# Important Source of Information nodegroup  (one tile)
IMPORTANT_SOURCE_NODEGROUP = "88ace5fb-927a-57b5-9aba-a63346e4e573"
NODE_IMPORTANT_SOURCE = "88ace5fb-927a-57b5-9aba-a63346e4e573"  # reference

# Permission to Interfere nodegroup  (one tile)
PERMISSION_NODEGROUP = "6452f897-1b16-5fc5-9fcd-e6d43f48ce49"
NODE_PERMISSION = "6452f897-1b16-5fc5-9fcd-e6d43f48ce49"  # reference

# Condition Assessment nodegroup  (contains date_of_assessment_start)
CONDITION_ASSESSMENT_NODEGROUP = "0b2fcd21-381d-11e8-b7d4-dca90488358a"
NODE_DATE_OF_ASSESSMENT_START = "0b2fdbc7-381d-11e8-ac6d-dca90488358a"  # date

# Archaeology Status nodegroup  (one tile)
ARCHAEOLOGY_STATUS_NODEGROUP = "6d658d05-857e-5aa3-b265-314f89e1804e"
NODE_ARCHAEOLOGY_STATUS = "6d658d05-857e-5aa3-b265-314f89e1804e"  # reference
ARCHAEOLOGY_STATUS_LIST_NAME = "Archaeology Status"

# Associated Monuments, Areas and Artefacts nodegroup  (one tile — resource-instance-list)
ASSOCIATED_MONUMENTS_NODEGROUP = "f019f44a-8639-11ea-988b-f875a44e0e11"
NODE_MONUMENT_AREA_OR_ARTEFACT = (
    "b0a53628-b539-11ea-8b11-f875a44e0e11"  # resource-instance-list
)

# Location Data nodegroup  (container — cleared on upsert along with child nodegroups)
LOCATION_DATA_NODEGROUP = "f7cc62b1-f447-11eb-bde0-a87eeabdefba"

# Location Descriptions nodegroup  (repeatable — child of Location Data)
LOCATION_DESCRIPTIONS_NODEGROUP = "f7cc62ab-f447-11eb-8614-a87eeabdefba"
NODE_LOCATION_DESCRIPTION = "f7cca086-f447-11eb-a4c4-a87eeabdefba"  # string

# Nodegroups whose tiles are fully replaced on each sync.
_MANAGED_NODEGROUPS = {
    SYSTEM_REF_NODEGROUP,
    ARTEFACT_NAMES_NODEGROUP,
    EXTERNAL_CROSS_REFS_NODEGROUP,
    DESCRIPTIONS_NODEGROUP,
    IMPORTANT_SOURCE_NODEGROUP,
    PERMISSION_NODEGROUP,
    CONDITION_ASSESSMENT_NODEGROUP,
    ARCHAEOLOGY_STATUS_NODEGROUP,
    ASSOCIATED_MONUMENTS_NODEGROUP,
    LOCATION_DATA_NODEGROUP,
    LOCATION_DESCRIPTIONS_NODEGROUP,
}

FINAL_STATUSES = {"final"}


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
    discovery_permit_number = payload.get("dpp_discoverypermitnumber")
    version_from_payload = payload.get("dpp_version")

    if not discovery_permit_number:
        raise ValueError("Missing required field: dpp_discoverypermitnumber")

    is_final = _is_final_payload(payload)

    current_draft_version = VersionedResource.objects.get_current_draft(
        discovery_permit_number
    )

    next_major, next_minor = calculate_next_version(
        current_draft_version,
        is_final,
        version_from_payload,
    )

    if not current_draft_version:
        resource = Resource()
        resource.graph_id = ARTEFACT_GRAPH_ID
        resource.tiles = _build_managed_tiles(payload, resource.pk)
        resource.save(user=user)

        register_new_draft(
            resource, discovery_permit_number, next_major, next_minor, payload
        )

        if is_final:
            finalize_draft(
                discovery_permit_number, user, next_major, next_minor, payload
            )

        return resource, True, f"{next_major}.{next_minor}"

    transaction_id = uuid.uuid4()
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

    models.TileModel.objects.filter(
        resourceinstance_id=current_draft_resource.pk,
        nodegroup_id__in=_MANAGED_NODEGROUPS,
    ).delete()

    current_draft_resource.tiles = _build_managed_tiles(
        payload, current_draft_resource.pk
    )
    current_draft_resource.save()

    if is_final:
        finalize_draft(discovery_permit_number, user, next_major, next_minor, payload)

    return current_draft_resource, False, f"{next_major}.{next_minor}"


def _is_final_payload(payload: dict) -> bool:
    return (payload.get("status") or "").lower() in FINAL_STATUSES


def _build_managed_tiles(payload: dict, resource_instance_ref: str) -> list:
    return (
        _build_system_ref_tile(payload)
        + _build_name_tiles(payload)
        + _build_external_ref_tiles(payload)
        + _build_description_tiles(payload)
        + _build_important_source_tile(payload)
        + _build_permission_tile(payload)
        + _build_condition_assessment_tile(payload)
        + _build_archaeology_status_tile(payload)
        + _build_associated_monuments_tile(payload)
        + _build_location_tiles(payload, resource_instance_ref)
    )


def _build_system_ref_tile(payload: dict) -> list:
    permit_number = payload.get("dpp_discoverypermitnumber")
    legacy_id = payload.get("dpp_discoveryreferencenumber")
    if not permit_number and not legacy_id:
        return []
    data = {}
    if permit_number is not None:
        data[NODE_PRIMARY_REF_NUM] = int(permit_number)
    if legacy_id is not None:
        data[NODE_LEGACY_ID] = i18n_string(str(legacy_id))
    return [make_tile(SYSTEM_REF_NODEGROUP, data)]


def _build_name_tiles(payload: dict) -> list:
    name = payload.get("dpp_discoveryname")
    if not name:
        return []
    return [
        make_tile(
            ARTEFACT_NAMES_NODEGROUP,
            {NODE_ARTEFACT_NAME: i18n_string(name)},
        )
    ]


def _build_external_ref_tiles(payload: dict) -> list:
    ref = payload.get("dpp_externalreferencenumber")
    if not ref:
        return []
    return [
        make_tile(
            EXTERNAL_CROSS_REFS_NODEGROUP,
            {NODE_EXTERNAL_CROSS_REF: i18n_string(str(ref))},
        )
    ]


def _build_description_tiles(payload: dict) -> list:
    tiles = []
    descriptions = [
        ("dpp_response", "Response"),
        ("dpp_descriptionsummary", "Summary"),
    ]
    for field, _type_label in descriptions:
        value = payload.get(field)
        if value:
            tiles.append(
                make_tile(
                    DESCRIPTIONS_NODEGROUP,
                    {
                        NODE_DESCRIPTION: i18n_string(value),
                        # TODO: map NODE_DESCRIPTION_TYPE to a reference node for _type_label
                    },
                )
            )
    return tiles


def _build_important_source_tile(payload: dict) -> list:
    value = payload.get("dpp_importantsourceofinformation")
    if value is None:
        return []
    # TODO: map integer value to a reference node
    return [
        make_tile(
            IMPORTANT_SOURCE_NODEGROUP,
            {NODE_IMPORTANT_SOURCE: parse_reference_node(value)},
        )
    ]


def _build_permission_tile(payload: dict) -> list:
    value = payload.get("dpp_permissiontointerferegranted")
    if value is None:
        return []
    # TODO: map integer value to a reference node
    return [
        make_tile(PERMISSION_NODEGROUP, {NODE_PERMISSION: parse_reference_node(value)})
    ]


def _build_condition_assessment_tile(payload: dict) -> list:
    date_value = payload.get("dpp_dateofdiscovery")
    if not date_value:
        return []
    return [
        make_tile(
            CONDITION_ASSESSMENT_NODEGROUP,
            {NODE_DATE_OF_ASSESSMENT_START: parse_date(date_value)},
        )
    ]


def _build_archaeology_status_tile(payload: dict) -> list:
    status = payload.get("dpp_archaeologystatus")
    if status is None:
        return []
    return [
        make_tile(
            ARCHAEOLOGY_STATUS_NODEGROUP,
            {
                NODE_ARCHAEOLOGY_STATUS: parse_reference_node(
                    status, ARCHAEOLOGY_STATUS_LIST_NAME
                )
            },
        )
    ]


def _build_associated_monuments_tile(payload: dict) -> list:
    items = payload.get("dpp_heritageitems", [])
    if not items:
        return []
    resource_instances = []
    for item in items:
        heritage_id_number = item.get("dpp_heritageidnumber")
        if heritage_id_number:
            print(
                "Looking up associated heritage item with ID number:",
                heritage_id_number,
            )
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
    return [
        make_tile(
            ASSOCIATED_MONUMENTS_NODEGROUP,
            {NODE_MONUMENT_AREA_OR_ARTEFACT: resource_instances},
        )
    ]


def _build_location_tiles(payload: dict, resource_instance_ref: str) -> list:
    locations = payload.get("dpp_locations", [])
    if not locations:
        return []

    try:
        location_data_tile = Tile.objects.get(
            resourceinstance_id=resource_instance_ref,
            nodegroup_id=LOCATION_DATA_NODEGROUP,
        )
    except Tile.DoesNotExist:
        location_data_tile = make_tile(LOCATION_DATA_NODEGROUP, {})

    tiles = [location_data_tile]

    for loc in locations:
        name = loc.get("cdm_name")
        if name:
            tiles.append(
                make_tile(
                    LOCATION_DESCRIPTIONS_NODEGROUP,
                    {NODE_LOCATION_DESCRIPTION: i18n_string(name)},
                    parent_tile_id=location_data_tile.tileid,
                )
            )

    gps_features = extract_gps_features(locations)
    if gps_features:
        # GPS features go into a geometry node if one exists; log a warning for now
        logger.warning(
            "GPS features found in artefact payload but no geometry node is mapped: %s",
            gps_features,
        )

    return tiles
