import logging

from arches.app.models import models
from arches.app.models.resource import Resource
from arches.app.utils.response import JSONErrorResponse, JSONResponse
from arches.app.views.resource import ResourceEditorView

from arches_resource_version_manager.lifecycle import archive_copy_of_current_draft
from arches_resource_version_manager.models import VersionedResource

from quartz.utils.payload_utils import i18n_string, make_tile, parse_resource_instance_id
from quartz.utils.upsert_dynamics_heritage_item import (
    VERSIONING_NODEGROUP,
    VERSION_NUMBER,
    WORKING_COPY,
)

logger = logging.getLogger(__name__)


class VersionedResourceEditorView(ResourceEditorView):

    def copy(self, request, resourceid=None):
        try:
            versioned_resource = VersionedResource.objects.get(pk=resourceid)
        except VersionedResource.DoesNotExist:
            return super().copy(request, resourceid)

        try:
            archived_version = archive_copy_of_current_draft(
                versioned_resource.resource_group_id, request.user
            )
            current_draft_version = VersionedResource.objects.get_current_draft(
                versioned_resource.resource_group_id
            )
            current_draft_version.minor_version = current_draft_version.minor_version + 1
            current_draft_version.save()

            current_draft_resource = Resource.objects.get(pk=current_draft_version.pk)
            models.TileModel.objects.filter(
                resourceinstance_id=current_draft_resource.pk,
                nodegroup_id=VERSIONING_NODEGROUP,
            ).delete()
            current_draft_resource.tiles = [
                make_tile(
                    VERSIONING_NODEGROUP,
                    {
                        VERSION_NUMBER: i18n_string(
                            f"{current_draft_version.major_version}.{current_draft_version.minor_version}"
                        ),
                        WORKING_COPY: parse_resource_instance_id(str(current_draft_resource.pk)),
                    },
                )
            ]
            current_draft_resource.save()

        except VersionedResource.DoesNotExist:
            return JSONErrorResponse(
                "Version Error",
                "No Draft version found for this resource group.",
                status=400,
            )

        return JSONResponse({"resourceid": str(archived_version.pk)})
