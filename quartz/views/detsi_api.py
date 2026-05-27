import logging
from django.db import transaction

from arches_resource_version_manager.views import ResourceVersionSyncView

from quartz.utils.upsert_dynamics_heritage_item import process_heritage_item

logger = logging.getLogger(__name__)


class DynamicsHeritageSyncView(ResourceVersionSyncView):
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

    def process_resource(self, payload: dict, user) -> tuple:
        resource_type = payload.get("resource_type")
        if resource_type == "heritage_item":
            with transaction.atomic():
                return process_heritage_item(payload, user)
        elif resource_type == "Archaeology Discovery":
            return self._upsert_archaeological_site(payload, user)
        else:
            raise ValueError(f"Unsupported resource_type: {resource_type}")
