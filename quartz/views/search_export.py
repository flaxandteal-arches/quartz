"""Search export with an added XML format.

Replaces the Arches ``search/export_results`` route. Every format except
``xml`` is handed straight to the Arches view, unchanged. ``xml`` exports the
Heritage Items in the current search that have Public visibility and whose
designation and protection status is Entered (the records on the public
website), written from the database with the logged-in user's nodegroup read
permissions applied. Anything else in the search results is skipped.
"""

import datetime
import logging
from io import BytesIO
from uuid import UUID

from django.http import HttpResponse
from django.urls import get_script_prefix, resolve, reverse
from django.utils.translation import gettext as _

from arches.app.models.system_settings import settings
from arches.app.utils.betterJSONSerializer import JSONDeserializer
from arches.app.utils.decorators import group_required
from arches.app.utils.permission_backend import get_nodegroups_by_perm
from arches.app.utils.response import JSONErrorResponse, JSONResponse
from arches.app.views import search as arches_search

logger = logging.getLogger(__name__)

XML_FORMAT = "xml"


class SearchFailed(Exception):
    pass


def get_search_resource_ids(request):
    """Resource ids matching the current search, as the Arches export does.

    Runs the same search as the results pane with ``export`` set so every page
    is returned (up to SEARCH_EXPORT_LIMIT), but without loading tiles.
    """
    request.GET = request.GET.copy()
    request.GET["export"] = True

    path = reverse("search_results")
    prefix = get_script_prefix()
    if path.startswith(prefix):
        path = path.replace(prefix, "/", 1)
    func, args, kwargs = resolve(path)
    kwargs["request"] = request
    response = func(*args, **kwargs)
    if response.status_code != 200:
        raise SearchFailed(f"search returned {response.status_code}")

    hits = JSONDeserializer().deserialize(response.content)["results"]["hits"]["hits"]
    return [UUID(hit["_id"]) for hit in hits]


def _nothing_to_export():
    return JSONResponse(
        {
            "success": False,
            "message": _(
                "None of the results are Public Heritage Items with status "
                "Entered, so there is nothing to export."
            ),
        }
    )


@group_required("Resource Exporter")
def export_results(request):
    if request.GET.get("format") != XML_FORMAT:
        return arches_search.export_results(request)

    from quartz.utils.public_xml_export import export_register_xml

    total = int(request.GET.get("total", 0))
    limit = settings.SEARCH_EXPORT_IMMEDIATE_DOWNLOAD_THRESHOLD
    if total > limit:
        # No background (Celery) path for XML yet.
        return JSONResponse(
            {
                "success": False,
                "message": _(
                    "Your search exceeds the {limit} instance limit for XML "
                    "export. Please refine your search."
                ).format(limit=limit),
            }
        )

    try:
        ids = get_search_resource_ids(request)
    except SearchFailed:
        logger.exception("XML export: search failed")
        return JSONErrorResponse(
            _("Export Failed"),
            _("There was an error retrieving the search results"),
            status=500,
        )
    if not ids:
        return JSONResponse({"success": False, "message": _("No resources to export.")})

    permitted = get_nodegroups_by_perm(request.user, "models.read_nodegroup")

    buffer = BytesIO()
    result = export_register_xml(ids, buffer, permitted_nodegroups=permitted)
    logger.info(
        "XML export by %s: %s places written, %s skipped (not a Heritage Item), "
        "%s skipped (not Public), %s skipped (not Entered)",
        request.user.username,
        result["count"],
        result["skipped_other_graph"],
        result["skipped_not_public"],
        result["skipped_not_entered"],
    )
    if result["count"] == 0:
        return _nothing_to_export()

    response = HttpResponse(
        buffer.getvalue(), content_type="application/xml; charset=utf-8"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="heritage-register-{datetime.date.today().isoformat()}.xml"'
    )
    return response
