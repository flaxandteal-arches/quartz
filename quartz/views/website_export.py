"""Endpoint behind the "Export to Website" button.

The server-side permission check here is the REAL access gate — the template
only hides the button. Requires ``quartz.export_to_website`` (granted to the
Delegate group; superusers pass automatically). Anyone without it gets 403.

POST dispatches the full public-export pipeline to a Celery worker
(run_public_export), so the request returns immediately with a task id.
"""

import logging

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_POST

from arches.app.utils.response import JSONErrorResponse, JSONResponse

logger = logging.getLogger(__name__)


@method_decorator(require_POST, name="dispatch")
class WebsiteExportView(PermissionRequiredMixin, View):
    # 403 (not a login redirect) for authenticated users lacking the perm.
    permission_required = "quartz.export_to_website"
    raise_exception = True

    def post(self, request):
        from django.conf import settings

        if not getattr(settings, "CELERY_BROKER_URL", ""):
            return JSONErrorResponse(
                title="Export not available",
                message=(
                    "Background export is not configured (no Celery broker). "
                    "Ask an administrator to enable it."
                ),
                status=503,
            )

        from quartz.tasks import run_public_export

        async_result = run_public_export.delay(push=True, trigger=True)
        logger.info(
            "Website export dispatched by %s: task %s",
            request.user.username,
            async_result.id,
        )
        return JSONResponse(
            {
                "task_id": async_result.id,
                "message": "Export to website started.",
            }
        )
