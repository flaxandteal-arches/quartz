import json
import logging
import uuid

from django.db import transaction

from arches.app.models import models
from arches.app.models.resource import Resource
from arches.app.utils.response import JSONErrorResponse, JSONResponse
from arches.app.views.resource import ResourceEditorView, ResourceEditLogView
from arches_resource_version_manager.lifecycle import (
    archive_copy_of_current_draft,
    finalize_draft,
)
from arches_resource_version_manager.models import VersionedResource

from quartz.utils.upsert_dynamics_heritage_item import (
    HERITAGE_ITEM_GRAPH_ID,
    increment_current_working_draft_version as increment_heritage_working_draft_version,
)
from quartz.utils.upsert_artefact import (
    ARTEFACT_GRAPH_ID,
    increment_current_working_draft_version as increment_artefact_working_draft_version,
)
from quartz.utils.versioned_resource_utils import increment_draft_version

logger = logging.getLogger(__name__)


class VersionedResourceEditorView(ResourceEditorView):

    def _increment_current_working_draft_version(self, current_draft_version):
        graph_id = str(current_draft_version.resourceinstance.graph_id)
        increment_fn = (
            increment_heritage_working_draft_version
            if graph_id == HERITAGE_ITEM_GRAPH_ID
            else increment_artefact_working_draft_version
        )
        return increment_fn(
            resourceid=current_draft_version.pk,
            major_version=current_draft_version.major_version,
            minor_version=current_draft_version.minor_version,
        )

    def get(self, request, **kwargs):
        resourceid = kwargs.get("resourceid")
        if self.action == "finalize_working_draft":
            return self.finalize_working_draft(request, resourceid)
        else:
            return super().get(request, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        resourceid = context.get("resourceid", "")
        graphid = str(context.get("graphid", ""))

        is_versioned = False
        is_working_draft = False
        can_create_final_version = self.request.user.has_perm(
            "arches_resource_version_manager.can_create_final_version"
        )

        if resourceid and graphid in [HERITAGE_ITEM_GRAPH_ID, ARTEFACT_GRAPH_ID]:
            vr = VersionedResource.objects.filter(
                resourceinstance_id=resourceid
            ).select_related(
                "resourceinstance__resource_instance_lifecycle_state",
            )
            if vr.exists():
                is_versioned = True
                resource = vr.first().resourceinstance
                if resource.resource_instance_lifecycle_state.name == "Draft":
                    is_working_draft = True

        context["is_versioned"] = is_versioned
        context["is_working_draft"] = is_working_draft
        context["can_create_final_version"] = can_create_final_version
        return context

    def copy(self, request, resourceid=None):
        try:
            current_draft_version = VersionedResource.objects.get(pk=resourceid)
            with transaction.atomic():
                transaction_id = uuid.uuid4()
                increment_draft_version(current_draft_version, is_final=False)
                current_draft_version.save()

                archived_version = archive_copy_of_current_draft(
                    current_draft_version.resource_group_id,
                    request.user,
                    transaction_id,
                )
                archived_resource = Resource.objects.get(pk=archived_version.pk)

                current_draft_resource = self._increment_current_working_draft_version(
                    current_draft_version
                )
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

    def finalize_working_draft(self, request, resourceid=None):
        try:
            current_draft_version = VersionedResource.objects.get(pk=resourceid)
            if (
                current_draft_version.resourceinstance.resource_instance_lifecycle_state.name
                != "Draft"
            ):
                return JSONErrorResponse(
                    "Only Draft versions can be finalized.", status=400
                )

            with transaction.atomic():
                transaction_id = uuid.uuid4()
                increment_draft_version(current_draft_version, is_final=True)
                current_draft_version.save()

                current_draft_resource = self._increment_current_working_draft_version(
                    current_draft_version
                )
                current_draft_resource.save(
                    transaction_id=transaction_id,
                    request=request,
                    user=request.user,
                )

                final = finalize_draft(
                    current_draft_version.resource_group_id,
                    request.user,
                    current_draft_version.major_version,
                    current_draft_version.minor_version,
                    None,
                )
                return JSONResponse({"resourceid": str(final.pk)})
        except VersionedResource.DoesNotExist:
            return JSONErrorResponse("VersionedResource not found.", status=404)


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
