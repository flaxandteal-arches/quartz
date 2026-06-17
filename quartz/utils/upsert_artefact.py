import logging
import uuid

from django.db.models import Max

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
    has_value,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Artefact graph and node constants
# ---------------------------------------------------------------------------

ARTEFACT_GRAPH_ID = "343cc20c-2c5a-11e8-90fa-0242ac120005"

# System Reference Numbers nodegroup  (one tile — not repeatable)
SYSTEM_REF_NODEGROUP = "dd800bc9-b494-11ea-9af8-f875a44e0e11"
NODE_PRIMARY_REF_NUM = "dd8032af-b494-11ea-8110-f875a44e0e11"  # number
NODE_LEGACY_ID = "dd8032b1-b494-11ea-a183-f875a44e0e11"  # string

# version information nodegroup (one tile — not repeatable)
VERSIONING_NODEGROUP = "07028e38-c27c-572f-8be5-e37ec837ad4f"
VERSION_NUMBER = "ddaac2c0-65f5-52ed-a843-43de724f9d01"  # string
# WORKING_COPY = "415b7f11-e007-56d6-a794-ba18aea7325b"  # reference to working draft

DEACTIVATION_REASON_NODEGROUP = "7def03f0-3bf7-52dc-b226-76b3d00bc8a2"
NODE_DEACTIVATION_REASON = "7def03f0-3bf7-52dc-b226-76b3d00bc8a2"  # string
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
NODE_DESCRIPTION_TYPE = "c30977b1-991e-11ea-b259-f875a44e0e11"  # reference\
DESCRIPTION_TYPE_LIST_NAME = "Description Roles"

# Important Source of Information nodegroup  (one tile)
IMPORTANT_SOURCE_NODEGROUP = "88ace5fb-927a-57b5-9aba-a63346e4e573"
NODE_IMPORTANT_SOURCE = "88ace5fb-927a-57b5-9aba-a63346e4e573"  # reference
IMPORTANT_SOURCE_LIST_NAME = "Important Source of Information"

# Permission to Interfere nodegroup  (one tile)
PERMISSION_NODEGROUP = "6452f897-1b16-5fc5-9fcd-e6d43f48ce49"
NODE_PERMISSION = "6452f897-1b16-5fc5-9fcd-e6d43f48ce49"  # reference
PERMISSION_LIST_NAME = "Permission to Interfere Previously Granted"

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

# Discovery nodegroup (container — not cleared on upsert; contains child nodegroups for different location types)
DISCOVERY_NODEGROUP = "28c9f728-2c5f-11e8-90fa-0242ac120005"

# Location Data nodegroup  (container — not cleared on upsert; contains child nodegroups for different location types)
LOCATION_DATA_NODEGROUP = "f7cc62b1-f447-11eb-bde0-a87eeabdefba"

# Addresses nodegroup  (repeatable — one tile per address; part of Location Data in UI)
ADDRESSES_NODEGROUP = "f7cc62a8-f447-11eb-9fae-a87eeabdefba"
NODE_FULL_ADDRESS = "f7cc8c72-f447-11eb-a7f5-a87eeabdefba"  # string
NODE_POSTCODE = "f7ccef67-f447-11eb-a0eb-a87eeabdefba"  # string
NODE_BUILDING_NUMBER = "f7cc8c85-f447-11eb-b1c8-a87eeabdefba"
NODE_STREET_NAME = "f7cca076-f447-11eb-8e8e-a87eeabdefba"
NODE_SUBURBS = ""
NODE_COUNTY = "f7ccef76-f447-11eb-ae38-a87eeabdefba"
NODE_LGA = ""
LGA_LIST_NAME = "LGAs"
SUBURB_LIST_NAME = "Suburbs"

# Geometry nodegroup  (one tile — all GPS points merged into one FeatureCollection)
GEOMETRY_NODEGROUP = "f7cc629f-f447-11eb-b2d3-a87eeabdefba"
NODE_GEOSPATIAL_COORDS = (
    "f7ccc8b9-f447-11eb-9cb1-a87eeabdefba"  # geojson-feature-collection
)

COORDINATE_SYSTEM_NODEGROUP = "f7cca095-f447-11eb-b171-a87eeabdefba"
NODE_COORDINATE_SYSTEM = "f7cc8c78-f447-11eb-9fc1-a87eeabdefba"
COORDINATE_SYSTEM_LIST_NAME = "SCS"

LOT_ON_PLAN_NODEGROUP = ""
NODE_LOT = ""  # dpp_lot
NODE_PLAN = ""  # dpp_plan

# Location Descriptions nodegroup  (repeatable — child of Location Data)
LOCATION_DESCRIPTIONS_NODEGROUP = "f7cc62ab-f447-11eb-8614-a87eeabdefba"
NODE_LOCATION_DESCRIPTION = "f7cca086-f447-11eb-a4c4-a87eeabdefba"  # string

# Nodegroups whose tiles are fully replaced on each sync.
_MANAGED_NODEGROUPS = {
    SYSTEM_REF_NODEGROUP,
    VERSIONING_NODEGROUP,
    DEACTIVATION_REASON_NODEGROUP,
    ARTEFACT_NAMES_NODEGROUP,
    EXTERNAL_CROSS_REFS_NODEGROUP,
    DESCRIPTIONS_NODEGROUP,
    IMPORTANT_SOURCE_NODEGROUP,
    PERMISSION_NODEGROUP,
    CONDITION_ASSESSMENT_NODEGROUP,
    ARCHAEOLOGY_STATUS_NODEGROUP,
    ASSOCIATED_MONUMENTS_NODEGROUP,
    ADDRESSES_NODEGROUP,
    GEOMETRY_NODEGROUP,
}

FINAL_STATUSES = {"recorded"}


def calculate_next_version(
    current_draft_version: VersionedResource, is_final: bool, version_from_payload: str
) -> tuple[int, int]:

    if is_final:
        current_major_version = (
            VersionedResource.objects.aggregate(Max("major_version"))[
                "major_version__max"
            ]
            or 0
        )

        major_version = current_major_version + 1
        return major_version, 0

    if current_draft_version is None:
        major_version = (
            int(version_from_payload) if version_from_payload is not None else 0
        )
        return major_version, 1
    else:
        return (
            current_draft_version.major_version,
            current_draft_version.minor_version + 1,
        )


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

        register_new_draft(resource, discovery_permit_number, 0, 0, payload)

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

    models.TileModel.objects.filter(
        resourceinstance_id=current_draft_resource.pk,
        nodegroup_id__in=_MANAGED_NODEGROUPS,
    ).delete()

    current_draft_resource.tiles = _build_managed_tiles(
        payload, next_major, next_minor, current_draft_resource.pk
    )
    current_draft_resource.save()

    if is_final:
        finalize_draft(discovery_permit_number, user, next_major, next_minor, payload)

    return current_draft_resource, created, f"{next_major}.{next_minor}"


def _is_final_payload(payload: dict) -> bool:
    return (payload.get("dpp_archaeologystatus") or "").lower() in FINAL_STATUSES


def _build_managed_tiles(
    payload: dict,
    major_version: str | int,
    minor_version: str | int,
    resource_instance_ref: str,
) -> list:
    return (
        _build_system_ref_tile(payload)
        + _build_version_tile(major_version, minor_version, resource_instance_ref)
        + _build_name_tiles(payload)
        + _build_external_ref_tiles(payload)
        + _build_description_tiles(payload)
        + _build_important_source_tile(payload)
        + _build_permission_tile(payload)
        + _build_condition_assessment_tile(payload)
        + _build_archaeology_status_tile(payload)
        + _build_deactivation_reason_tile(payload)
        + _build_associated_monuments_tile(payload)
        + _build_location_tiles(payload, resource_instance_ref)
    )


def _build_version_tile(
    major_version: str | int, minor_version: str | int, resource_instance_ref: str
) -> list:
    return [
        make_tile(
            VERSIONING_NODEGROUP,
            {VERSION_NUMBER: i18n_string(f"{major_version}.{minor_version}")},
        )
    ]


def _build_system_ref_tile(payload: dict) -> list:
    permit_number = payload.get("dpp_permitnumber")
    legacy_id = payload.get("dpp_discoveryreferencenumber")
    if not has_value(permit_number) and not has_value(legacy_id):
        return []
    data = {}
    if has_value(permit_number):
        data[NODE_PRIMARY_REF_NUM] = int(permit_number)
    if has_value(legacy_id):
        data[NODE_LEGACY_ID] = i18n_string(str(legacy_id))
    return [make_tile(SYSTEM_REF_NODEGROUP, data)]


def _build_name_tiles(payload: dict) -> list:
    name = payload.get("dpp_discoveryname")
    if not has_value(name):
        return []
    return [
        make_tile(
            ARTEFACT_NAMES_NODEGROUP,
            {NODE_ARTEFACT_NAME: i18n_string(name)},
        )
    ]


def _build_external_ref_tiles(payload: dict) -> list:
    ref = payload.get("dpp_externalreferencenumber")
    if not has_value(ref):
        return []
    return [
        make_tile(
            EXTERNAL_CROSS_REFS_NODEGROUP,
            {NODE_EXTERNAL_CROSS_REF: i18n_string(str(ref))},
        )
    ]


def _build_deactivation_reason_tile(payload: dict) -> list:
    reason = payload.get("dpp_deactivationreason")
    if not has_value(reason):
        return []
    return [
        make_tile(
            DEACTIVATION_REASON_NODEGROUP,
            {
                NODE_DEACTIVATION_REASON: parse_reference_node(
                    reason, DEACTIVATION_REASON_LIST_NAME
                )
            },
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
        if has_value(value):
            tiles.append(
                make_tile(
                    DESCRIPTIONS_NODEGROUP,
                    {
                        NODE_DESCRIPTION: i18n_string(value),
                        NODE_DESCRIPTION_TYPE: parse_reference_node(
                            _type_label, DESCRIPTION_TYPE_LIST_NAME
                        ),
                    },
                )
            )
    return tiles


def _build_important_source_tile(payload: dict) -> list:
    value = payload.get("dpp_importantsourceofinformation")
    if not has_value(value):
        return []
    # TODO: map integer value to a reference node
    return [
        make_tile(
            IMPORTANT_SOURCE_NODEGROUP,
            {
                NODE_IMPORTANT_SOURCE: parse_reference_node(
                    value, IMPORTANT_SOURCE_LIST_NAME
                )
            },
        )
    ]


def _build_permission_tile(payload: dict) -> list:
    value = payload.get("dpp_permissiontointerferegranted")
    if not has_value(value):
        return []
    # TODO: map integer value to a reference node
    return [
        make_tile(
            PERMISSION_NODEGROUP,
            {NODE_PERMISSION: parse_reference_node(value, PERMISSION_LIST_NAME)},
        )
    ]


def _build_condition_assessment_tile(payload: dict) -> list:
    date_value = payload.get("dpp_dateofdiscovery")
    if not has_value(date_value):
        return []
    return [
        make_tile(
            CONDITION_ASSESSMENT_NODEGROUP,
            {NODE_DATE_OF_ASSESSMENT_START: parse_date(date_value)},
        )
    ]


def _build_archaeology_status_tile(payload: dict) -> list:
    status = payload.get("dpp_archaeologystatus")
    if not has_value(status):
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
    tiles = []

    try:
        location_data_tile = Tile.objects.get(
            resourceinstance_id=resource_instance_ref,
            nodegroup_id=LOCATION_DATA_NODEGROUP,
        )
    except Tile.DoesNotExist:
        try:
            discovery_tile = Tile.objects.get(
                resourceinstance_id=resource_instance_ref,
                nodegroup_id=DISCOVERY_NODEGROUP,
            )
        except Tile.DoesNotExist:
            discovery_tile = make_tile(DISCOVERY_NODEGROUP, {})
            tiles.append(discovery_tile)

        location_data_tile = make_tile(
            LOCATION_DATA_NODEGROUP, {}, parent_tile_id=discovery_tile.tileid
        )
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
                    # (NODE_LGA, lga, lambda v: parse_reference_node(v, LGA_LIST_NAME)),
                    (NODE_POSTCODE, postcode, i18n_string),
                    (NODE_BUILDING_NUMBER, street_number, i18n_string),
                    (NODE_STREET_NAME, street_name_full, i18n_string),
                    # (
                    #     NODE_SUBURBS,
                    #     suburb,
                    #     lambda v: parse_reference_node(v, SUBURB_LIST_NAME),
                    # ),
                    (NODE_COUNTY, state, i18n_string),
                ]
                if has_value(val)
            }

            if data:
                tiles.append(
                    make_tile(
                        ADDRESSES_NODEGROUP,
                        data,
                        parent_tile_id=location_data_tile.tileid,
                    )
                )

        # if loc.get("location_type") == "Lot Plan":
        #     lot = loc.get("dpp_lot")
        #     plan = loc.get("dpp_plan")
        #     if lot or plan:
        #         tiles.append(
        #             make_tile(
        #                 LOT_ON_PLAN_NODEGROUP,
        #                 {
        #                     NODE_LOT: i18n_string(lot),
        #                     NODE_PLAN: i18n_string(plan),
        #                 },
        #                 parent_tile_id=location_data_tile.tileid,
        #             )
        #         )

        if loc.get("location_type") == "GPS":
            gps_features = extract_gps_features([loc])
            geometry_tile = make_tile(
                GEOMETRY_NODEGROUP,
                {
                    NODE_GEOSPATIAL_COORDS: {
                        "type": "FeatureCollection",
                        "features": gps_features,
                    }
                },
                parent_tile_id=location_data_tile.tileid,
            )
            tiles.append(
                make_tile(
                    COORDINATE_SYSTEM_NODEGROUP,
                    {
                        NODE_COORDINATE_SYSTEM: parse_reference_node(
                            loc.get("dpp_spatialcoordinatesystem"),
                            COORDINATE_SYSTEM_LIST_NAME,
                        )
                    },
                    parent_tile_id=geometry_tile.tileid,
                )
            )
            tiles.append(geometry_tile)

    return tiles
