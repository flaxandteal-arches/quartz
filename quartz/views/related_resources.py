"""Related-resources view that lists each versioned resource once.

Every archive/finalize copies the whole resource, tiles included, so each
version carries its own resource_x_resource rows and core lists the same item
once per version. This view, routed ahead of arches.urls, leaves out the rows
that superseded versions hold. Intended to move into arches_resource_version_manager.
"""

from collections import defaultdict
from uuid import UUID

from django.db.models import Count, F, Q
from django.forms.models import model_to_dict
from django.utils.translation import get_language
from django.utils.translation import gettext as _

from arches.app.models import models
from arches.app.models.resource import Resource
from arches.app.models.system_settings import settings
from arches.app.search.mappings import RESOURCES_INDEX
from arches.app.search.search_engine_factory import SearchEngineInstance as se
from arches.app.utils import permission_backend
from arches.app.utils.permission_backend import get_filtered_instances
from arches.app.utils.resource_relationship_utils import (
    get_resource_relationship_type_label,
)
from arches.app.utils.response import JSONResponse
from arches.app.utils.string_utils import str_to_bool
from arches.app.views.resource import RelatedResourcesView
from arches_resource_version_manager.models import VersionedResource


def _in_state(name):
    # State ids are fetched first: a subquery that joins the i18n `name` column
    # fails when Django relabels it inside the outer query.
    state_ids = list(
        models.ResourceInstanceLifecycleState.objects.filter(name=name).values_list(
            "id", flat=True
        )
    )
    return Q(resourceinstance__resource_instance_lifecycle_state_id__in=state_ids)


def superseded_version_ids(keep_id):
    """Retired versions, and Active versions whose group has a Draft; never keep_id."""
    drafted_groups = VersionedResource.objects.filter(_in_state("Draft")).values(
        "resource_group_id"
    )
    return (
        VersionedResource.objects.filter(
            _in_state("Retired")
            | (_in_state("Active") & Q(resource_group_id__in=drafted_groups))
        )
        .exclude(resourceinstance_id=keep_id)
        .values("resourceinstance_id")
    )


def merged_related_resources(
    self,
    lang="en-US",
    limit=settings.RELATED_RESOURCES_EXPORT_LIMIT,
    start=0,
    page=0,
    user=None,
    resourceinstance_graphid=None,
    graphs=None,
    include_rr_count=True,
):
    """Core Resource.get_related_resources (arches 8.2.0a8) minus superseded versions.

    Copied verbatim (self is the resource) because core builds its relation
    query in a nested function; only relations differs. Re-copy on upgrade.
    """

    # Only the from end: a row belongs to the resource whose tile holds it, so the
    # copies' rows start at the copy. A link another resource makes to a specific
    # version is that resource's own row and must stay. A Draft's working_copy
    # points at itself, so self-links are left out too.
    relations = models.ResourceXResource.objects.exclude(
        from_resource__in=superseded_version_ids(self.pk)
    ).exclude(from_resource=F("to_resource"))

    # TODO This function is very similar to code in search results and the resource view. Needs to be centralized.
    def get_localized_descriptor(document, descriptor_type):
        language_codes = (get_language(), settings.LANGUAGE_CODE)
        descriptor = document["_source"][descriptor_type]
        result = descriptor[0] if len(descriptor) > 0 else {"value": _("Undefined")}
        for language_code in language_codes:
            for entry in descriptor:
                if entry["language"] == language_code and entry["value"] != "":
                    return entry["value"]
        return result["value"]

    if not graphs:
        graphs = list(
            models.GraphModel.objects.all()
            .exclude(pk=settings.SYSTEM_SETTINGS_RESOURCE_MODEL_ID)
            .exclude(isresource=False)
            .exclude(is_active=False)
            .exclude(source_identifier__isnull=False)
        )

    graph_lookup = {
        str(graph.graphid): {
            "name": graph.name,
            "iconclass": graph.iconclass,
            "fillColor": graph.color,
        }
        for graph in graphs
    }

    ret = {
        "resource_instance": self,
        "resource_relationships": [],
        "related_resources": [],
        "node_config_lookup": graph_lookup,
    }

    if page > 0:
        number_per_page = settings.RELATED_RESOURCES_PER_PAGE
        start = number_per_page * int(page - 1)
        limit = number_per_page * page

    def get_relations(
        resourceinstanceid,
        start,
        limit,
        resourceinstance_graphid=None,
    ):
        final_query = Q(from_resource_id=resourceinstanceid) | Q(
            to_resource_id=resourceinstanceid
        )

        if resourceinstance_graphid:
            to_graph_id_filter = Q(from_resource_graph_id=str(self.graph_id)) & Q(
                to_resource_graph_id=resourceinstance_graphid
            )
            from_graph_id_filter = Q(
                from_resource_graph_id=resourceinstance_graphid
            ) & Q(to_resource_graph_id=str(self.graph_id))
            final_query = final_query & (to_graph_id_filter | from_graph_id_filter)

        return {  # resourceinstance_graphid = "00000000-886a-374a-94a5-984f10715e3a"
            "total": relations.filter(final_query).count(),
            "relations": relations.filter(final_query)[start:limit],
        }

    resource_relations = get_relations(
        resourceinstanceid=self.resourceinstanceid,
        start=start,
        limit=limit,
        resourceinstance_graphid=resourceinstance_graphid,
    )

    ret["total"] = {"value": resource_relations["total"]}
    instanceids = set()

    readable_graphids = set(
        permission_backend.get_resource_types_by_perm(user, ["models.read_nodegroup"])
    )
    all_resource_ids = set()
    for relation in resource_relations["relations"]:
        all_resource_ids.add(str(relation.to_resource_id))
        all_resource_ids.add(str(relation.from_resource_id))
    exclusive_set, filtered_instances = get_filtered_instances(
        user, se, resources=list(all_resource_ids)
    )
    filtered_instances = filtered_instances if user is not None else []
    permitted_relation_dicts = []

    for relation in resource_relations["relations"]:
        relation = model_to_dict(relation)
        to_resource = relation["to_resource"]
        from_resource = relation["from_resource"]
        to_resource_graph = relation["to_resource_graph"]
        from_resource_graph = relation["from_resource_graph"]

        resourceid_to_permission = str(to_resource) not in filtered_instances
        resourceid_from_permission = str(from_resource) not in filtered_instances

        if exclusive_set:
            resourceid_to_permission = not (resourceid_to_permission)
            resourceid_from_permission = not (resourceid_from_permission)

        if (
            resourceid_to_permission
            and resourceid_from_permission
            and str(to_resource_graph) in readable_graphids
            and str(from_resource_graph) in readable_graphids
        ):
            permitted_relation_dicts.append(relation)
        else:
            ret["total"]["value"] -= 1

    # Fetch pref labels for relationship types in bulk.
    relationship_types = {
        relation["relationshiptype"]
        for relation in permitted_relation_dicts
        if relation["relationshiptype"]
    }

    preflabel_lookup = get_resource_relationship_type_label(relationship_types, lang)

    for relation in permitted_relation_dicts:
        relation["relationshiptype_label"] = preflabel_lookup.get(
            relation["relationshiptype"], relation["relationshiptype"] or ""
        )

        ret["resource_relationships"].append(relation)
        instanceids.add(str(relation["to_resource"]))
        instanceids.add(str(relation["from_resource"]))

    if str(self.resourceinstanceid) in instanceids:
        instanceids.remove(str(self.resourceinstanceid))

    if len(instanceids) > 0:
        related_resources = se.search(index=RESOURCES_INDEX, id=list(instanceids))
        if related_resources:
            related_resource_ids = [
                resource["_id"]
                for resource in related_resources["docs"]
                if resource["found"]
            ]
            if include_rr_count:
                to_counts = (
                    relations.filter(to_resource__in=related_resource_ids)
                    .values("to_resource")
                    .annotate(to_count=Count("to_resource"))
                    # ORDER BY NULLS LAST is necessary for "pipelined" GROUP BY, see
                    # https://use-the-index-luke.com/sql/sorting-grouping/indexed-group-by
                    .order_by(F("to_resource").asc(nulls_last=True))
                )
                from_counts = (
                    relations.filter(from_resource__in=related_resource_ids)
                    .values("from_resource")
                    .annotate(from_count=Count("from_resource"))
                    .order_by(F("from_resource").asc(nulls_last=True))
                )

                total_relations_by_resource_id: dict[UUID:int] = defaultdict(int)
                for related_resource_count in to_counts:
                    total_relations_by_resource_id[
                        related_resource_count["to_resource"]
                    ] += related_resource_count["to_count"]
                for related_resource_count in from_counts:
                    total_relations_by_resource_id[
                        related_resource_count["from_resource"]
                    ] += related_resource_count["from_count"]

            for resource in related_resources["docs"]:
                if resource["found"]:
                    if include_rr_count:
                        resource["_source"]["total_relations"] = {
                            "value": total_relations_by_resource_id[
                                UUID(resource["_id"])
                            ]
                        }
                    for descriptor_type in ("displaydescription", "displayname"):
                        descriptor = get_localized_descriptor(resource, descriptor_type)
                        if descriptor:
                            resource["_source"][descriptor_type] = descriptor
                        else:
                            resource["_source"][descriptor_type] = _("Undefined")

                    ret["related_resources"].append(resource["_source"])

    return ret


class MergedVersionRelatedResourcesView(RelatedResourcesView):
    """RelatedResourcesView whose listings come from merged_related_resources."""

    def related(self, request, resource, **kwargs):
        kwargs.update(
            lang=request.GET.get("lang", request.LANGUAGE_CODE),
            user=request.user,
            resourceinstance_graphid=request.GET.get("resourceinstance_graphid"),
        )
        if not str_to_bool(request.GET.get("paginate", "true")):
            return merged_related_resources(resource, **kwargs)
        page = 1 if request.GET.get("page") == "" else int(request.GET.get("page", 1))
        related = merged_related_resources(
            resource, start=int(request.GET.get("start", 0)), page=page, **kwargs
        )
        return self.paginate_related_resources(related, page, request)

    def get(self, request, resourceid=None, include_rr_count=True, graphs=None):
        resource = Resource.objects.get(pk=resourceid)
        return JSONResponse(
            self.related(
                request, resource, include_rr_count=include_rr_count, graphs=graphs
            )
        )

    # Core's post and delete write the change, then answer with the refreshed
    # list; the write is kept and the list is rebuilt merged.
    def post(self, request, resourceid=None):
        super().post(request, resourceid)
        resource = Resource.objects.get(pk=request.POST["root_resourceinstanceid"])
        return JSONResponse(self.related(request, resource), indent=4)

    def delete(self, request, resourceid=None):
        super().delete(request, resourceid)
        resource = Resource.objects.get(pk=request.GET["root_resourceinstanceid"])
        return JSONResponse(self.related(request, resource), indent=4)
