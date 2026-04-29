import json
import logging
import uuid

from django.utils.decorators import method_decorator
from django.views.generic import View

from arches.app.utils.decorators import group_required
from arches.app.utils.response import JSONResponse


logger = logging.getLogger(__name__)


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


# @method_decorator(csrf_exempt, name="dispatch")
# @method_decorator(group_required("DETSI_API"), name="dispatch")
class DynamicsHeritageSyncView(View):
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
            resourceinstanceid, created = self._upsert_heritage_item(
                payload, request.user
            )
        except Exception:
            logger.exception("Error processing Dynamics heritage payload")
            return JSONResponse(
                {"error": "Internal server error — see server logs for details"},
                status=500,
            )

        return JSONResponse(
            {
                "resourceinstanceid": str(resourceinstanceid),
                "created": created,
                "graph_id": HERITAGE_ITEM_GRAPH_ID,
            },
            status=201 if created else 200,
        )

    def _upsert_heritage_item(self, payload: dict, user) -> tuple:
        # placeholder implementation to allow testing of API endpoint and
        # response handling in Dynamics integration workstream;
        # to be replaced with actual upsert logic in subsequent PR

        return uuid.uuid4(), True
