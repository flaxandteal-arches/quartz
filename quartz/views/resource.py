import json
import logging
import uuid

from django.db import transaction

from arches.app.models import models
from arches.app.models.resource import Resource
from arches.app.utils.response import JSONErrorResponse, JSONResponse
from arches.app.views.resource import ResourceEditorView, ResourceEditLogView

from arches_resource_version_manager.lifecycle import archive_copy_of_current_draft
from arches_resource_version_manager.models import VersionedResource

from quartz.utils.payload_utils import (
    i18n_string,
    make_tile,
    parse_resource_instance_id,
)
from quartz.utils.upsert_dynamics_heritage_item import (
    HERITAGE_ITEM_GRAPH_ID,
    VERSIONING_NODEGROUP,
    VERSION_NUMBER,
    WORKING_COPY,
)

logger = logging.getLogger(__name__)


class VersionedResourceEditorView(ResourceEditorView):

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        resourceid = context.get("resourceid", "")
        graphid = str(context.get("graphid", ""))

        is_versioned = False
        is_working_draft = False

        if resourceid and graphid == HERITAGE_ITEM_GRAPH_ID:
            is_versioned = True
            tile = models.TileModel.objects.filter(
                resourceinstance_id=resourceid,
                nodegroup_id=VERSIONING_NODEGROUP,
            ).first()
            if tile:
                working_copy_refs = tile.data.get(WORKING_COPY, [])
                if working_copy_refs:
                    is_working_draft = str(
                        working_copy_refs[0].get("resourceId", "")
                    ) == str(resourceid)

        context["is_versioned"] = is_versioned
        context["is_working_draft"] = is_working_draft
        return context

    def copy(self, request, resourceid=None):
        try:
            versioned_resource = VersionedResource.objects.get(pk=resourceid)
            transaction_id = uuid.uuid4()
            archived_version = archive_copy_of_current_draft(
                versioned_resource.resource_group_id, request.user, transaction_id
            )
            archived_resource = Resource.objects.get(pk=archived_version.pk)
            current_draft_version = VersionedResource.objects.get_current_draft(
                versioned_resource.resource_group_id
            )
            current_draft_version.minor_version = (
                current_draft_version.minor_version + 1
            )
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
                        WORKING_COPY: parse_resource_instance_id(
                            str(current_draft_resource.pk)
                        ),
                    },
                )
            ]
            current_draft_resource.save(
                transaction_id=transaction_id,
                request=request,
                user=request.user,
                edit_log_type="copy",
                edit_log_note="Archived to",
                edit_log_newvalue={
                    "resourceinstanceid": str(archived_resource.pk),
                    "descriptors": archived_resource.descriptors,
                },
            )
            return JSONResponse({"resourceid": str(archived_version.pk)})

        except VersionedResource.DoesNotExist:
            return super().copy(request, resourceid)


class VersionedResourceEditLogView(ResourceEditLogView):

    def get(self, request, resourceid=None):
        return super().get(
            request,
            resourceid=resourceid,
            view_template="views/resource/versioned-edit-log.htm",
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        resourceid = kwargs.get("resourceid")

        version_tree_data = None
        if resourceid:
            try:
                current_version = VersionedResource.objects.select_related(
                    "resourceinstance__resource_instance_lifecycle_state",
                ).get(pk=resourceid)

                siblings = (
                    VersionedResource.objects.filter(
                        resource_group_id=current_version.resource_group_id,
                    )
                    .select_related(
                        "resourceinstance__resource_instance_lifecycle_state",
                    )
                    .order_by("created_at")
                )

                version_tree_data = json.dumps(
                    [
                        {
                            "resourceinstanceid": str(version.pk),
                            "major_version": version.major_version,
                            "minor_version": version.minor_version,
                            "version_label": f"{version.major_version}.{version.minor_version}",
                            "lifecycle_state": str(
                                version.resourceinstance.resource_instance_lifecycle_state.name
                            ),
                            "created_at": version.created_at.isoformat(),
                            "is_current": str(version.pk) == str(resourceid),
                            "display_name": str(version.resourceinstance.name),
                        }
                        for version in siblings
                    ]
                )
            except VersionedResource.DoesNotExist:
                pass

        context["version_tree_data"] = version_tree_data
        return context
