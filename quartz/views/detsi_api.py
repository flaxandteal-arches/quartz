import json
import logging
import uuid
from datetime import datetime

from oauth2_provider.views.generic import ProtectedResourceView
from oauth2_provider.models import AccessToken

from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from arches.app.models import models
from arches.app.models.resource import Resource
from arches.app.models.tile import Tile
from arches.app.utils.decorators import group_required
from arches.app.utils.response import JSONResponse

from quartz.models import HeritageItemState

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

# System Reference Numbers nodegroup  (repeatable)
SYSTEM_REF_NODEGROUP = "325a2f2f-efe4-11eb-9b0c-a87eeabdefba"
NODE_LEGACY_ID = "325a441c-efe4-11eb-9283-a87eeabdefba"  # string
NODE_LEGACY_ID_TYPE = "325a441b-efe4-11eb-872d-a87eeabdefba"  # reference
NODE_PRIMARY_REF_NUM = "325a2f33-efe4-11eb-b0bb-a87eeabdefba"  # number

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

# Descriptions nodegroup  (repeatable — one tile per description entry)
DESCRIPTIONS_NODEGROUP = "ba342e69-b554-11ea-a027-f875a44e0e11"
NODE_DESCRIPTION = "ba345577-b554-11ea-a9ee-f875a44e0e11"  # string
NODE_DESCRIPTION_TYPE = "ba34557b-b554-11ea-ab95-f875a44e0e11"  # reference

# External Cross References nodegroup  (repeatable — one tile per lot/plan)
EXTERNAL_XREF_NODEGROUP = "f17f6581-efc7-11eb-b09f-a87eeabdefba"
NODE_EXTERNAL_XREF = "f17f6584-efc7-11eb-81f1-a87eeabdefba"  # string
NODE_EXTERNAL_XREF_SOURCE = "f17f658a-efc7-11eb-a216-a87eeabdefba"  # reference


# ---------------------------------------------------------------------------
# Payload state constants
# ---------------------------------------------------------------------------

# Dynamics status values that represent a "Final" (published) record.
# TODO: confirm exact Dynamics status values with the Dynamics team.
FINAL_STATUSES: frozenset = frozenset(["final"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _i18n_string(value: str) -> dict:
    """Wrap a plain string in Arches 8 i18n format."""
    return {"en": {"value": value, "direction": "ltr"}}


def _parse_date(value: str):
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


def _make_tile(
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


# ---------------------------------------------------------------------------
# Resource lifecycle stubs  (cloning not yet available)
# ---------------------------------------------------------------------------


def _clone_resource(resource: Resource):
    """
    Clone a Resource and return the new copy.
    NOT YET IMPLEMENTED — cloning support is pending.
    """
    return resource.copy()
    logger.warning(
        "Resource cloning is not yet implemented (resource %s will not be cloned).",
        resource.resourceinstanceid,
    )
    raise NotImplementedError("Resource cloning is not yet implemented.")


def _archive_and_copy_current_draft(heritage_id_number, user) -> None:
    """
    Mark a Draft Resource as archived (no longer editable or promotable to Final).
    """

    try:
        current_heritage_item_state = HeritageItemState.objects.get(
            heritage_id_number=heritage_id_number,
            state=HeritageItemState.DRAFT,
            editable=True,
        )
    except HeritageItemState.DoesNotExist:
        raise ValueError(
            f"No editable Draft HeritageItemState found for {heritage_id_number!r}."
        )

    # Archive a clone of the Draft before updating it (stub).
    draft_resource = models.Resource.objects.get(
        resourceinstanceid=current_heritage_item_state.resourceinstanceid_id
    )
    draft_clone = draft_resource.copy()
    draft_clone.resource_instance_lifecycle_state = (
        models.ResourceInstanceLifecycleState.objects.get(name="Retired")
    )
    draft_clone.save(user=user)

    HeritageItemState.objects.create(
        heritage_id_number=heritage_id_number,
        resourceinstanceid=draft_clone,
        version=current_heritage_item_state.version,
        payload=current_heritage_item_state.payload,
        editable=False,
        state=HeritageItemState.ARCHIVED,
    )

    return draft_resource


def _archive_final_resource(heritage_id_number, user) -> None:
    """
    Mark a Final Resource as archived (no longer editable or promotable to Final).
    """
    try:
        heritage_item = HeritageItemState.objects.get(
            heritage_id_number=heritage_id_number,
            state=HeritageItemState.FINAL,
        )
    except HeritageItemState.DoesNotExist:
        raise ValueError(
            f"No Final HeritageItemState found for {heritage_id_number!r}."
        )
    heritage_item.state = HeritageItemState.ARCHIVED
    heritage_item.editable = False
    heritage_item.save()


@method_decorator(csrf_exempt, name="dispatch")
class DynamicsHeritageSyncView(ProtectedResourceView):
    """
    POST /api/dynamics/heritage-item/

    Accepts a Dynamics 365 heritage-item JSON payload and creates or updates
    the corresponding Heritage Item resource instance in Arches.

    Field mapping source: dynamics-arches-field-mapping.json

    Returns:
        201  { "resourceinstanceid": "...", "created": true,  "graph_id": "..." }
        200  { "resourceinstanceid": "...", "created": false, "graph_id": "..." }
        400  { "error": "..." }
        500  { "error": "..." }
    """

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body)
        except (json.JSONDecodeError, ValueError) as exc:
            return JSONResponse({"error": f"Invalid JSON: {exc}"}, status=400)

        try:
            auth_header = request.headers.get("Authorization", "")
            token_str = auth_header.replace("Bearer ", "")
            try:
                token = AccessToken.objects.get(token=token_str)
            except AccessToken.DoesNotExist:
                return JSONResponse({"error": "Invalid token"}, status=401)
            application = token.application
            resource, created = self._upsert_heritage_item(payload, application.user)
        except Exception:
            logger.exception("Error processing Dynamics heritage payload")
            return JSONResponse(
                {"error": "Internal server error — see server logs for details"},
                status=500,
            )

        return JSONResponse(
            {
                "resourceinstanceid": str(resource.resourceinstanceid),
                "created": created,
                "graph_id": HERITAGE_ITEM_GRAPH_ID,
            },
            status=201 if created else 200,
        )

    # ------------------------------------------------------------------
    # Upsert logic
    # ------------------------------------------------------------------

    # Nodegroups whose tiles are fully replaced on each sync.
    # Includes Location Data and all its UI child nodegroups (Addresses, Geometry, etc.).
    _STATUTORY_NODEGROUPS = {
        NAMES_NODEGROUP,
        SYSTEM_REF_NODEGROUP,
        LOCATION_DATA_NODEGROUP,
        ADDRESSES_NODEGROUP,
        GEOMETRY_NODEGROUP,
        DESCRIPTIONS_NODEGROUP,
        EXTERNAL_XREF_NODEGROUP,
    }

    def _upsert_heritage_item(self, payload: dict, user) -> tuple:
        """
        Implements the Payload API logical data flow:

        New item (6000 number not in HeritageItemState):
          - Create a Draft Resource from the payload.
          - Add a Draft entry to HeritageItemState.

        Existing item (6000 number found in HeritageItemState):
          - Look up the latest Draft resource.
          - Clone the Draft for archival before mutating it (stub).
          - Update the Draft resource with the incoming payload data.
          - If the payload is Final:
            - Archive the current Final resource, if any (stub).
            - Clone the updated Draft as the new Final resource (stub).
            - Add a Final entry to HeritageItemState.

        Returns (resource, created_bool).
        """
        heritage_id_number = payload.get("dpp_heritageidnumber")
        version = payload.get("dpp_version")
        item_state = payload.get("status").lower() if payload.get("status") else None

        if not heritage_id_number:
            raise ValueError("Missing required field: dpp_heritageidnumber")

        if item_state not in HeritageItemState.STATE_CHOICES:
            raise ValueError(
                f"Invalid status value: {item_state!r} (must be one of {list(HeritageItemState.STATE_CHOICES.keys())})"
            )

        is_final = self._is_final_payload(payload)

        # ------------------------------------------------------------------
        # Is the 6000 number in the Heritage Item State table?
        # ------------------------------------------------------------------
        existing_heritage_item = HeritageItemState.objects.filter(
            heritage_id_number=heritage_id_number
        ).exists()

        if not existing_heritage_item:
            # New item: create a Draft Resource and record it in the state table.
            resource = Resource()
            resource.graph_id = HERITAGE_ITEM_GRAPH_ID
            tiles = self._build_tiles(payload)
            resource.tiles = tiles
            resource.save(user=user)

            HeritageItemState.objects.create(
                heritage_id_number=heritage_id_number,
                resourceinstanceid=resource,
                version=version,
                payload=payload,
                editable=True,
                state=HeritageItemState.DRAFT,
            )

            return resource, True

        # ------------------------------------------------------------------
        # Existing item: find the latest Draft resource.
        # ------------------------------------------------------------------
        # try:
        #     draft_heritage_item = HeritageItemState.objects.get(
        #         heritage_id_number=heritage_id_number,
        #         state=HeritageItemState.DRAFT,
        #         editable=True,
        #     )
        # except HeritageItemState.DoesNotExist:
        #     raise ValueError(
        #         f"HeritageItemState entry exists for {heritage_id_number!r} "
        #         "but no Draft version was found."
        #     )

        current_draft_resource = _archive_and_copy_current_draft(
            heritage_id_number, user
        )

        # Update the Draft resource with data from the incoming payload.
        models.TileModel.objects.filter(
            resourceinstance_id=current_draft_resource.pk,
            nodegroup_id__in=self._STATUTORY_NODEGROUPS,
        ).delete()

        tiles = self._build_tiles(payload)
        for tile in tiles:
            tile.resourceinstance_id = current_draft_resource.pk
            tile.save(
                resource=current_draft_resource, request=None, index=False, user=user
            )

        current_draft_resource.save_descriptors()
        current_draft_resource.index()

        # ------------------------------------------------------------------
        # If the payload is Final, promote to a Final resource.
        # ------------------------------------------------------------------
        if is_final:
            # Archive the current Final resource if one exists.
            final_state = (
                HeritageItemState.objects.filter(
                    heritage_id_number=heritage_id_number,
                    state=HeritageItemState.FINAL,
                )
                .order_by("-created_at")
                .first()
            )
            if final_state:
                current_final = Resource.objects.get(
                    resourceinstanceid=final_state.resourceinstanceid_id
                )
                current_final.resource_instance_lifecycle_state = (
                    models.ResourceInstanceLifecycleState.objects.get(name="Retired")
                )
                current_final.save(user=user)
                _archive_final_resource(heritage_id_number)

            # Clone the updated Draft as the new Final (stub).
            final_resource = current_draft_resource.copy()
            active_state = models.ResourceInstanceLifecycleState.objects.get(
                name="Active"
            )
            final_resource.resource_instance_lifecycle_state = active_state
            final_resource.save(user=user)

            HeritageItemState.objects.create(
                heritage_id_number=heritage_id_number,
                resourceinstanceid=final_resource,
                state=HeritageItemState.FINAL,
                payload=payload,
                editable=False,
            )

        return current_draft_resource, False

    def _is_final_payload(self, payload: dict) -> bool:
        """Return True if the Dynamics payload represents a Final (published) record."""
        return payload.get("status").lower() in FINAL_STATUSES

    # ------------------------------------------------------------------
    # Tile construction
    # ------------------------------------------------------------------

    def _build_tiles(self, payload: dict) -> list:
        tiles = []

        # --- System Reference Numbers: heritage ID number ---
        # Mapping: dpp_heritageidnumber → Monument.PlaceReference / legacy_id
        heritage_id = payload.get("dpp_heritageidnumber")
        if heritage_id:
            tiles.append(
                _make_tile(
                    SYSTEM_REF_NODEGROUP,
                    {NODE_LEGACY_ID: _i18n_string(heritage_id)},
                )
            )

        # --- Primary name ---
        # Mapping: dpp_name → HeritageItem.Name
        primary_name = payload.get("dpp_name")
        if primary_name:
            tiles.append(
                _make_tile(
                    NAMES_NODEGROUP,
                    {NODE_NAME: _i18n_string(primary_name)},
                    sortorder=0,
                )
            )

        # --- Alternative names ---
        # Mapping: alternative_names[].dpp_name → HeritageItem.AlternateName
        # The alternative names field sometimes concatenates multiple names with " | ".
        for alt in payload.get("alternative_names", []):
            alt_name = alt.get("dpp_name")
            if alt_name:
                for index, part in enumerate(alt_name.split(" | ")):
                    part = part.strip()
                    if part:
                        tiles.append(
                            _make_tile(
                                NAMES_NODEGROUP,
                                {NODE_NAME: _i18n_string(part)},
                                sortorder=index + 1,
                            )
                        )

        # create LOCATION_DATA_NODEGROUP tile (container for all location-related child nodegroups)
        location_data_parent_tile = _make_tile(LOCATION_DATA_NODEGROUP, {})
        tiles.append(location_data_parent_tile)

        # --- Addresses  (Location Data → Addresses in UI) ---
        # Mapping: Locations[location_type=Address].cdm_name → Address.full_address
        for loc in payload.get("Locations", []):
            if loc.get("location_type") == "Address":
                address = loc.get("cdm_name")
                if address:
                    tiles.append(
                        _make_tile(
                            ADDRESSES_NODEGROUP,
                            {NODE_FULL_ADDRESS: _i18n_string(address)},
                            parent_tile_id=location_data_parent_tile.tileid,
                        )
                    )

        # --- Lot / Plan as External Cross References ---
        # Mapping: Locations[location_type=dpp_lot dpp_plan].cdm_name → Parcel.Lot+Plan
        # for loc in payload.get("Locations", []):
        #     if loc.get("location_type") == "dpp_lot dpp_plan":
        #         lot_plan = loc.get("cdm_name")
        #         if lot_plan:
        #             tiles.append(
        #                 _make_tile(
        #                     EXTERNAL_XREF_NODEGROUP,
        #                     {NODE_EXTERNAL_XREF: lot_plan},
        #                     parent_tile_id=location_data_parent_tile.tileid,
        #                 )
        #             )

        # --- GPS coordinates → GeoJSON FeatureCollection  (Location Data → Geometry in UI) ---
        # Mapping: Locations[location_type=GPS] → geospatial_coordinates
        gps_features = []
        for loc in payload.get("Locations", []):
            if loc.get("location_type") == "GPS":
                lat = loc.get("dpp_latitude")
                lon = loc.get("dpp_longitude")

                if lat is None or lon is None:
                    # Fallback: parse "lat,lon" string from cdm_name
                    cdm_name = loc.get("cdm_name", "")
                    try:
                        lat_str, lon_str = cdm_name.split(",", 1)
                        lat, lon = float(lat_str.strip()), float(lon_str.strip())
                    except (ValueError, AttributeError):
                        logger.warning(
                            "Could not parse GPS coords from cdm_name: %r", cdm_name
                        )
                        continue

                try:
                    gps_features.append(
                        {
                            "type": "Feature",
                            "geometry": {
                                "type": "Point",
                                # GeoJSON: [longitude, latitude]
                                "coordinates": [float(lon), float(lat)],
                            },
                            "properties": {},
                        }
                    )
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Invalid GPS values lat=%r lon=%r: %s", lat, lon, exc
                    )

        if gps_features:
            tiles.append(
                _make_tile(
                    GEOMETRY_NODEGROUP,
                    {
                        NODE_GEOSPATIAL_COORDS: {
                            "type": "FeatureCollection",
                            "features": gps_features,
                        }
                    },
                    parent_tile_id=location_data_parent_tile.tileid,
                )
            )

        # --- Status ---
        # Mapping: status → Monument status
        # NOTE: A formal concept-value mapping between Dynamics status values and
        # Arches reference nodes has not yet been defined (see field mapping notes).
        # Stored as a free-text description until the mapping is resolved.
        status = payload.get("status")
        if status:
            tiles.append(
                _make_tile(
                    DESCRIPTIONS_NODEGROUP,
                    {NODE_DESCRIPTION: _i18n_string(f"Heritage Item Status: {status}")},
                )
            )

        # --- Dates ---
        # NOTE: Target Arches nodes for these dates are marked unknown in the
        # field mapping spreadsheet.  Stored as free-text descriptions pending
        # resolution of the correct node assignments.
        #
        # Mapping: dpp_dateenteredregister → Monument.EnteredCalculated
        date_entered = _parse_date(payload.get("dpp_dateenteredregister"))
        if date_entered:
            tiles.append(
                _make_tile(
                    DESCRIPTIONS_NODEGROUP,
                    {
                        NODE_DESCRIPTION: _i18n_string(
                            f"Date Entered Register: {date_entered}"
                        )
                    },
                )
            )

        # Mapping: dpp_dateremovedfromregister → Monument.RemovedCalculated
        date_removed = _parse_date(payload.get("dpp_dateremovedfromregister"))
        if date_removed:
            tiles.append(
                _make_tile(
                    DESCRIPTIONS_NODEGROUP,
                    {
                        NODE_DESCRIPTION: _i18n_string(
                            f"Date Removed from Register: {date_removed}"
                        )
                    },
                )
            )

        # Mapping: dpp_qhcdecisiondate → UNKNOWN (marked '?' in spreadsheet)
        qhc_date = _parse_date(payload.get("dpp_qhcdecisiondate"))
        if qhc_date:
            tiles.append(
                _make_tile(
                    DESCRIPTIONS_NODEGROUP,
                    {NODE_DESCRIPTION: _i18n_string(f"QHC Decision Date: {qhc_date}")},
                )
            )

        return tiles
